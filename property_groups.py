import bpy
from .constants import DIFFUSION_MODELS, CONTROLNET_MODELS, T2I_MODELS

def parse_sd_models(models):
    return [(model.id, model.label, '') for model in models]

class ControlNetListItem(bpy.types.PropertyGroup):
    def from_controlnet_models(self, context):
        return [(id, model_info['name'], '') for id, model_info in CONTROLNET_MODELS.items()]
    
    controlnet_model: bpy.props.EnumProperty(name='', items=from_controlnet_models) # type: ignore
    controlnet_image_slot: bpy.props.PointerProperty(name='', type=bpy.types.Image) # type: ignore
    controlnet_factor: bpy.props.FloatProperty(name='', min=0.0, max=5.0, step=0.05, default=0.5) # type: ignore

class T2iListItem(bpy.types.PropertyGroup):
    def from_t2i_models(self, context):
        return [(id, model_info['name'], '') for id, model_info in T2I_MODELS.items()]
    
    t2i_model: bpy.props.EnumProperty(name='', items=from_t2i_models) # type: ignore
    t2i_image_slot: bpy.props.PointerProperty(name='', type=bpy.types.Image) # type: ignore
    t2i_factor: bpy.props.FloatProperty(name='', min=0.0, max=5.0, step=0.05, default=0.5) # type: ignore

class UDPropertyGroup(bpy.types.PropertyGroup):
    model: bpy.props.EnumProperty(items=parse_sd_models(DIFFUSION_MODELS), name="Model") # type: ignore
    prompt: bpy.props.StringProperty(name="Prompt", default="A close up of a cat with sunglasses driving a ferrari, golden hour") # type: ignore
    negative_prompt: bpy.props.StringProperty(name="Negative Prompt") # type: ignore
    scale: bpy.props.IntProperty(
        name='Scale',
        soft_max=1000,
        default=50,
        min=0,
    ) # type: ignore
    width: bpy.props.IntProperty(
        name='Width',
        soft_max=10000,
        default=1920,
        min=0,
    ) # type: ignore
    height: bpy.props.IntProperty(
        name='Height',
        soft_max=10000,
        default=1080,
        min=0,
    ) # type: ignore
    seed: bpy.props.IntProperty(
        name='Seed',
        soft_max=99999,
        default=0,
        soft_min=0,
    ) # type: ignore
    inference_steps: bpy.props.IntProperty(
        name='Inference steps',
        soft_max=100,
        default=50,
        min=1,
    ) # type: ignore
    cfg_scale: bpy.props.FloatProperty(
        name='CFG scale',
        soft_max=100,
        default=5,
        min=0,
        precision=1,
    ) # type: ignore
    init_image_slot: bpy.props.PointerProperty(
        name="Init Image",
        description="Enter the slot for an init image to condition the generation",
        type=bpy.types.Image
    ) # type: ignore
    init_mask_slot: bpy.props.PointerProperty(
        name="Mask Image",
        description="Enter the slot for a masking image for the inpainting generation",
        type=bpy.types.Image
    ) # type: ignore
    denoise_strength: bpy.props.FloatProperty(
        name='Denoising Strength',
        max=1,
        default=0.4,
        min=0,
        precision=2,
    ) # type: ignore
    control_mode: bpy.props.StringProperty(
        name='Control Mode',
        default='controlnet'
    ) # type: ignore

    controlnet_list : bpy.props.CollectionProperty(type=ControlNetListItem) # type: ignore
    t2i_list : bpy.props.CollectionProperty(type=T2iListItem) # type: ignore
    control_list_index : bpy.props.IntProperty(
        default=-1,
        update=lambda self, context: setattr(self, 'control_list_index', -1)
    ) # type: ignore

    running: bpy.props.BoolProperty(name="is running", default=0) # type: ignore
    progress: bpy.props.IntProperty(name="", min=0, max=100, default=0) # type: ignore
    progress_text: bpy.props.StringProperty(name="") # type: ignore
    stop_process: bpy.props.BoolProperty(name="stop", default=0) # type: ignore

    ## Utilities
    canny_strength: bpy.props.FloatProperty(
        name='Canny Strength',
        max=1,
        default=0.5,
        min=0,
        precision=2,
    ) # type: ignore