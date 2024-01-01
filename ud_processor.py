from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLControlNetPipeline, StableDiffusionXLPipeline, StableDiffusionUpscalePipeline, StableDiffusionXLImg2ImgPipeline, StableDiffusionXLInpaintPipeline, StableDiffusionXLControlNetInpaintPipeline, StableDiffusionXLControlNetImg2ImgPipeline, ControlNetModel, AutoencoderKL

import bpy
import numpy as np
import torch
# import debugpy
from PIL import Image, ImageEnhance
from realesrgan_ncnn_py import Realesrgan
from . import gpudetector


# Install opencv-python-headless instead of regular opencv-python! Or you'll run into xcb conflicts

def round_to_nearest(n):
    if n - int(n) < 0.5:
        return int(n)
    else:
        return int(n) + 1
    
def blender_image_to_pil(blender_image):
    # Ensure the image is not None
    if blender_image is None:
        raise ValueError("No Blender image provided")

    # Get the image data as a numpy array
    pixels = np.array(blender_image.pixels[:])  # Flatten pixel values
    size = blender_image.size[0], blender_image.size[1]  # Image dimensions

    # Reshape and convert the array to a suitable format
    pixels = np.reshape(pixels, (size[1], size[0], 4))  # Assuming RGBA
    pixels = np.flip(pixels, axis=0)  # Flip the image vertically
    pixels = (pixels * 255).astype(np.uint8)  # Convert to 8-bit per channel

    # Create and return a PIL image
    return Image.fromarray(pixels, 'RGBA')

from PIL import Image

def create_alpha_mask(image):

    if image.mode != 'RGBA':
        raise ValueError("Image does not have an alpha channel")

    alpha = image.split()[-1]
    inverted_alpha = Image.eval(alpha, lambda a: 255 - a)

    mask = inverted_alpha.convert('L')

    return mask

def is_mask_almost_black(mask, tolerance=5):

    if mask.mode != 'L':
        mask = mask.convert('L')

    mask_array = np.array(mask)
    avg_pixel = np.mean(mask_array)

    return avg_pixel < tolerance

class UD_Processor():
    prompt_adds = ", highly detailed, beautiful, 4K, photorealistic, high resolution"
    negative_prompt_adds = ", text, watermark, low-quality, signature, moiré pattern, downsampling, aliasing, distorted, blurry, glossy, blur, jpeg artifacts, compression artifacts, poorly drawn, bad, distortion, twisted, grainy, duplicate, error, pixelated, fake, glitch, overexposed, bad-contrast"
    refiner_model = "stabilityai/stable-diffusion-xl-refiner-1.0"
    vae_model = "madebyollin/sdxl-vae-fp16-fix"

    upscale_strength = 0.35
    upscaling_rate = 2
    upscaling_steps = 10

    loaded_model = None
    loaded_model_type = None
    loaded_vae = None
    loaded_controlnets = None

    def run(self, params):
        # debugpy.listen
        target_width = round((params['width'] * params['scale'] / 100) / 8) * 8
        target_height = round((params['height'] * params['scale'] / 100) / 8) * 8

        init_image = blender_image_to_pil(params['init_image_slot']).resize((target_width, target_height)) if params.get('init_image_slot') else None

        if params['init_mask_slot']:
            mask_image = blender_image_to_pil(params['init_mask_slot']).resize((target_width, target_height)).convert("RGB")
        else:
            if init_image:
                mask_image = create_alpha_mask(init_image)
                if is_mask_almost_black(mask_image):
                    mask_image = None
            else:
                mask_image = None
            
        controlnet_image = [Image.open(path).resize((target_width, target_height)).convert("RGB") for path in params['controlnet_image_path']] if params.get('controlnet_image_path') else None

        overrides={
            'prompt': params['prompt'] + self.prompt_adds,
            'negative_prompt': params['negative_prompt'] + self.negative_prompt_adds,
            'width': target_width,
            'height': target_height,
            'generator': torch.manual_seed(params["seed"]),
        }

        params['steps_multiplier'] = 0.1 if 'turbo' in params['model'] else 1

        if 'controlnet_model' in params:
            if mask_image and init_image:
                pipeline_type = 'StableDiffusionXLControlNetInpaintPipeline'
            else:
                pipeline_type = 'StableDiffusionXLControlNetImg2ImgPipeline' if init_image else 'StableDiffusionXLControlNetPipeline'
            overrides.update({
                'image': init_image if init_image else controlnet_image,
                'controlnet_conditioning_scale': params['controlnet_conditioning_scale'],
            })
            if init_image:
                overrides.update({
                    'strength': params['denoise_strength'],
                    'num_inference_steps': round_to_nearest(params['inference_steps'] / params['denoise_strength']),
                    'control_image': controlnet_image,
                })

        else:
            if mask_image and init_image:
                pipeline_type = 'StableDiffusionXLInpaintPipeline'
            else:
                pipeline_type = 'StableDiffusionXLImg2ImgPipeline' if init_image else 'StableDiffusionXLPipeline'
            overrides.update({
                'denoising_end': params['high_noise_frac']
                })
            if init_image:
                overrides.update({
                    'image': init_image.convert("RGB"),
                    'num_inference_steps': round_to_nearest(params['inference_steps'] / params['denoise_strength']),
                    'strength': params['denoise_strength'],
                })

        if init_image and mask_image:
            overrides.update({
                'mask_image': mask_image,
            })

        latent_image = self.run_pipeline(
            params=params,
            pipeline_type=pipeline_type,
            pipeline_model=params['model'],
            vae_model=self.vae_model,
            controlnet_models=params.get('controlnet_model', []),
            overrides=overrides
        )

        if latent_image is not None:
            if params['high_noise_frac'] < 1:
            # Start Refining
                overrides = {
                    'prompt': params['prompt'] + self.prompt_adds,
                    'negative_prompt': params['negative_prompt'] + ' hdr ' + self.negative_prompt_adds,
                    'image': latent_image,
                    'strength': params['refiner_strength'],
                }

                if 'controlnet_model' not in params:
                    overrides['denoising_start'] = params['high_noise_frac']
                    overrides['num_inference_steps'] = int (params['inference_steps'])
                else:
                    overrides['num_inference_steps'] =  round_to_nearest(params['inference_steps'] / params['refiner_strength'])

                decoded_image = self.run_pipeline(
                    params=params,
                    pipeline_type='StableDiffusionXLImg2ImgPipeline',
                    pipeline_model=self.refiner_model,
                    vae_model=self.vae_model,
                    overrides=overrides,
                    output_type='pil'
                )
            else:
                with torch.no_grad():
                    image = self.pipe.vae.decode(latent_image / self.pipe.vae.config.scaling_factor, return_dict=False)[0]
                    decoded_image = self.pipe.image_processor.postprocess(image, output_type="pil")[0]
            
            return decoded_image
        else:
            return None

    def upscale(self, params): 

        image = Image.open(params['temp_image_filepath'])

        current_width = round_to_nearest(params['width']/8)*8
        current_height = round_to_nearest(params['height']/8)*8
        
        params['steps_multiplier'] = 0.5 if 'turbo' in params['model'] else 1

        if params['mode'] == 'upscale_re':
            # Resize to 4x using realesrgan
            realesrgan = Realesrgan(gpuid = gpudetector.get_nvidia_gpu(), model = 4)
            image = realesrgan.process_pil(image)
            realesrgan = None
            upscaled_image = image.resize((current_width * 4, current_height * 4), Image.Resampling.LANCZOS)
            contrast=1.1

        elif params['mode'] == 'upscale_sd':
            # Resize to 4x using stable-diffusion-x4-upscaler
            self.unload()   
            model_id = "stabilityai/stable-diffusion-x4-upscaler"
            self.pipe = StableDiffusionUpscalePipeline.from_pretrained(model_id, torch_dtype=torch.float16)
            self.pipe = self.pipe.to("cuda")
            self.pipe.enable_attention_slicing()
            upscaled_image = self.pipe(
                    prompt=params['prompt'],
                    image=image.convert("RGB"),
                    noise_level=5,
                    num_inference_steps=25,
                ).images[0]
            upscaled_image = upscaled_image.resize((current_width * 2, current_height * 2), Image.Resampling.LANCZOS)
            contrast=1.1

        # Enhance the contrast by 10% as the upscale reduces the contrast
        enhancer = ImageEnhance.Contrast(upscaled_image)
        upscaled_image = enhancer.enhance(contrast)

        upscaled_image.save(params['temp_image_filepath'])

        # Refine upscaled image
        overrides = {
                'prompt': params['prompt'] + self.prompt_adds,
                'negative_prompt': params['negative_prompt'] + ' hdr ' + self.negative_prompt_adds,
                'image': upscaled_image.convert('RGB'),
                'strength': self.upscale_strength,
                'num_inference_steps': round_to_nearest(self.upscaling_steps / self.upscale_strength),
                'guidance_scale': 5,
            }

        for model in [params['model']]:
            decoded_image = self.run_pipeline(
                params=params,
                pipeline_type='StableDiffusionXLImg2ImgPipeline',
                pipeline_model=model,
                vae_model=self.vae_model,
                overrides=overrides,
                output_type='pil'
            )
        return decoded_image

    def run_pipeline(
            self,
            params,
            pipeline_type,
            pipeline_model, 
            vae_model = None,
            controlnet_models = [],
            overrides = {},
            show_image = True,
            output_type = 'latent',
        ):

        with torch.no_grad(): 
            # Initializing dict with common parameters
            pipe_params = {
                'prompt': params['prompt'],
                'negative_prompt': params['negative_prompt'],
                'num_inference_steps': params['inference_steps'],
                'guidance_scale': params['cfg_scale'],
            }
            pipe_params.update(overrides)

            # CONTROLNET
            if self.loaded_controlnets != controlnet_models:
                if len(controlnet_models) == 0:
                    self.loaded_controlnets = []
                else:
                    controlnets = [self.create_controlnet(controlnet) for controlnet in controlnet_models]
                    self.loaded_controlnets = controlnets

            # PIPELINE AND VAE
            if pipeline_model in ['stablediffusionapi/NightVision_XL']:
                vae_model = None

            if self.loaded_model != pipeline_model or self.loaded_model_type != pipeline_type or self.loaded_vae != vae_model:

                model_params = {
                    'torch_dtype': torch.float16,
                    'add_watermarker': False,
                }

                if vae_model:
                    self.vae = AutoencoderKL.from_pretrained( vae_model, torch_dtype=torch.float16 ).to("cuda")
                    self.loaded_vae = vae_model
                    model_params['vae'] = self.vae

                try:
                    try:
                        self.pipe = globals()[pipeline_type].from_pretrained(pipeline_model, **model_params, variant= 'fp16')
                        print("Loaded fp16 weights")
                    except Exception as e2:
                        print(f"Failed with variant='fp16'. Falling back to original parameters.")
                        self.pipe = globals()[pipeline_type].from_pretrained(pipeline_model, **model_params)

                    self.pipe.to("cuda")
                    self.pipe.enable_vae_tiling()

                except Exception as e:
                    print(f"UD: Error occurred in loading the pipeline:\n\n{e}")
                    self.unload()
                    return None

                self.loaded_model = pipeline_model
                self.loaded_model_type = pipeline_type

            # CALCULATED SETTINGS
            pipe_params['num_inference_steps'] = int(pipe_params['num_inference_steps'] * params['steps_multiplier'])

            # SPECIAL SETTINGS FOR SOME MODELS
            if 'sdxl-turbo' in pipeline_model:
                pipe_params['guidance_scale'] = 0

            print(self.loaded_model + ' ' + self.loaded_model_type)

            # RUN STABLE DIFFUSION
            try:
                latent_image = self.pipe(
                    **pipe_params,
                    output_type='latent',
                ).images
            except Exception as e:
                print(f"UD: Error occurred while running the pipeline:\n\n{e}")
                self.unload()
                return None

            if show_image == True or output_type == 'pil':
                with torch.no_grad():
                    image = self.pipe.vae.decode(latent_image / self.pipe.vae.config.scaling_factor, return_dict=False)[0]
                    decoded_image = self.pipe.image_processor.postprocess(image, output_type="pil")[0]
            
                    decoded_image.save(params['temp_image_filepath'])

            if output_type == 'latent':
                return latent_image
            elif output_type == 'pil':
                return decoded_image
        
    def create_controlnet(self, controlnet_model):
        return ControlNetModel.from_pretrained(
            controlnet_model,
            variant="fp16",
            use_safetensors=True,
            torch_dtype=torch.float16,
        ).to("cuda")        

    def unload(self):

        for item in ['pipe','vae']:
            if hasattr(self, item):
                getattr(self, item).to('cpu')
                delattr(self, item)

        torch.cuda.empty_cache()

        self.loaded_model = None
        self.loaded_model_type = None
        self.loaded_vae = None
        self.loaded_controlnets = None

        print("GPU cache has been cleared.")