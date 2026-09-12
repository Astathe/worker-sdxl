# Start from the official RunPod worker-comfyui base image
FROM runpod/worker-comfyui:5.1.0-base

# =============================================================================
# Install Custom Nodes
# =============================================================================
# We use the GitHub URLs to ensure we get exactly the repos previously installed.
RUN comfy-node-install \
    https://github.com/Comfy-Org/ComfyUI-Manager \
    https://github.com/ltdrdata/ComfyUI-Impact-Pack \
    https://github.com/ltdrdata/ComfyUI-Impact-Subpack \
    https://github.com/yolain/ComfyUI-Easy-Use \
    https://github.com/ssitu/ComfyUI_UltimateSDUpscale \
    https://github.com/rgthree/rgthree-comfy \
    https://github.com/alexopus/ComfyUI-Image-Saver \
    https://github.com/kijai/ComfyUI-KJNodes \
    https://github.com/willmiao/ComfyUI-Lora-Manager \
    https://github.com/pythongosssss/ComfyUI-Custom-Scripts \
    https://github.com/Miosp/ComfyUI-FBCNN \
    https://github.com/Fannovel16/comfyui_controlnet_aux \
    https://github.com/cubiq/ComfyUI_IPAdapter_plus \
    https://github.com/KohakuBlueleaf/z-tipo-extension \
    https://github.com/pamparamm/ComfyUI-ppm \
    https://github.com/1038lab/ComfyUI-QwenVL \
    https://github.com/mirabarukaso/ComfyUI_Mira \
    https://github.com/shadowcz007/comfyui-mixlab-nodes

# =============================================================================
# Download Models
# =============================================================================
# Checkpoint
RUN comfy model download --url https://huggingface.co/LyliaEngine/waiIllustriousSDXL_v170/resolve/main/waiIllustriousSDXL_v170.safetensors --relative-path models/checkpoints --filename waiIllustriousSDXL_v170.safetensors

# LoRA
RUN comfy model download --url "https://huggingface.co/Astathe/uma/resolve/main/UmaDiffusionXL_4th.safetensors?download=true" --relative-path models/loras --filename UmaDiffusionXL_4th.safetensors

# VAE
RUN comfy model download --url https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors --relative-path models/vae/SDXL --filename sdxl_vae.safetensors

# ControlNet
RUN comfy model download --url https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-canny-rank256.safetensors --relative-path models/controlnet/SDXL --filename control-lora-canny-rank256.safetensors
RUN comfy model download --url https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-depth-rank256.safetensors --relative-path models/controlnet/SDXL --filename control-lora-depth-rank256.safetensors
RUN comfy model download --url https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors --relative-path models/controlnet/SDXL --filename OpenPoseXL2.safetensors
RUN comfy model download --url https://huggingface.co/Acly/NoobAI-Inpainting/resolve/main/noobaiInpainting_v10.fp16.safetensors --relative-path models/controlnet --filename noobaiInpainting_v10.fp16.safetensors

# IP-Adapter
RUN comfy model download --url https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors --relative-path models/ipadapter --filename ip-adapter-plus_sdxl_vit-h.safetensors
RUN comfy model download --url https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin --relative-path models/ipadapter --filename ip-adapter-faceid-plusv2_sdxl.bin

# CLIP Vision
RUN comfy model download --url https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K/resolve/main/open_clip_pytorch_model.safetensors --relative-path models/clip_vision --filename CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors
RUN comfy model download --url https://huggingface.co/stabilityai/control-lora/resolve/main/revision/clip_vision_g.safetensors --relative-path models/clip_vision --filename clip_vision_g.safetensors

# Upscale Models
RUN comfy model download --url https://huggingface.co/FacehugmanIII/4x_foolhardy_Remacri/resolve/main/4x_foolhardy_Remacri.pth --relative-path models/upscale_models --filename 4x_foolhardy_Remacri.pth

# SAM Models
RUN comfy model download --url https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth --relative-path models/sams --filename sam_vit_b_01ec64.pth

# Ultralytics (Bbox / Segm)
RUN comfy model download --url https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov9c.pt --relative-path models/ultralytics/bbox --filename hand_yolov9c.pt
RUN comfy model download --url https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov9c.pt --relative-path models/ultralytics/bbox --filename face_yolov9c.pt
RUN comfy model download --url https://huggingface.co/GritTin/LoraStableDiffusion/resolve/c7766cc3c9b8b4f914932ce27f1cd48f25434636/Eyeful_v2-Paired.pt --relative-path models/ultralytics/bbox --filename Eyeful_v2-Paired.pt
RUN comfy model download --url https://huggingface.co/adbrasi/wanlotest/resolve/main/ntd11_anime_nsfw_segm_v5-variant1.pt --relative-path models/ultralytics/segm --filename ntd11_anime_nsfw_segm_v5-variant1.pt
RUN comfy model download --url https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-seg.pt --relative-path models/ultralytics/segm --filename yolo11m-seg.pt

# =============================================================================
# RunPod SDK and Custom Handler
# =============================================================================
# Install dependencies
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# Copy handler, workflow, and startup script
WORKDIR /
COPY handler.py /handler.py
COPY start.sh /start.sh
COPY ["Advanced_Gemma_V38 UMA.json", "/workflow.json"]
COPY ["Advanced_Gemma_V38 UMA API.json", "/workflow_api.json"]
RUN chmod +x /start.sh

# Start using the custom handler
CMD ["/start.sh"]
