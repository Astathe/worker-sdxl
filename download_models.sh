#!/bin/bash
set -euo pipefail

# =============================================================================
# Download all required models for the Advanced_Gemma_V38 UMA ComfyUI workflow
# =============================================================================

COMFY_DIR="${COMFY_DIR:-/ComfyUI}"

# Helper: download with aria2c (fast, resumable, retries)
download() {
    local url="$1"
    local dest_dir="$2"
    local filename="${3:-}"

    mkdir -p "$dest_dir"

    if [ -n "$filename" ]; then
        if [ -f "$dest_dir/$filename" ]; then
            echo "[SKIP] $dest_dir/$filename already exists"
            return 0
        fi
        echo "[DOWNLOAD] $url -> $dest_dir/$filename"
        aria2c --console-log-level=error --summary-interval=5 \
            -x 16 -s 16 -k 1M \
            --max-tries=5 --retry-wait=3 \
            -d "$dest_dir" -o "$filename" \
            "$url"
    else
        echo "[DOWNLOAD] $url -> $dest_dir/"
        aria2c --console-log-level=error --summary-interval=5 \
            -x 16 -s 16 -k 1M \
            --max-tries=5 --retry-wait=3 \
            -d "$dest_dir" \
            "$url"
    fi
}

echo "=============================================="
echo "  Downloading models for ComfyUI workflow"
echo "=============================================="

# -----------------------------------------------------------------------------
# Checkpoint
# -----------------------------------------------------------------------------
echo ""
echo ">>> Checkpoint: waiIllustriousSDXL_v170"
download \
    "https://huggingface.co/LyliaEngine/waiIllustriousSDXL_v170/resolve/main/waiIllustriousSDXL_v170.safetensors" \
    "$COMFY_DIR/models/checkpoints" \
    "waiIllustriousSDXL_v170.safetensors"

# -----------------------------------------------------------------------------
# LoRA
# -----------------------------------------------------------------------------
echo ""
echo ">>> LoRA"
download \
    "https://civitai.com/api/download/models/1930892?fileId=1829094" \
    "$COMFY_DIR/models/loras" \
    "civitai_lora_1930892.safetensors"

# -----------------------------------------------------------------------------
# VAE
# -----------------------------------------------------------------------------
echo ""
echo ">>> VAE: sdxl_vae"
mkdir -p "$COMFY_DIR/models/vae/SDXL"
download \
    "https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors" \
    "$COMFY_DIR/models/vae/SDXL" \
    "sdxl_vae.safetensors"

# -----------------------------------------------------------------------------
# ControlNet
# -----------------------------------------------------------------------------
echo ""
echo ">>> ControlNet models"
mkdir -p "$COMFY_DIR/models/controlnet/SDXL"

download \
    "https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-canny-rank256.safetensors" \
    "$COMFY_DIR/models/controlnet/SDXL" \
    "control-lora-canny-rank256.safetensors"

download \
    "https://huggingface.co/stabilityai/control-lora/resolve/main/control-LoRAs-rank256/control-lora-depth-rank256.safetensors" \
    "$COMFY_DIR/models/controlnet/SDXL" \
    "control-lora-depth-rank256.safetensors"

download \
    "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors" \
    "$COMFY_DIR/models/controlnet/SDXL" \
    "OpenPoseXL2.safetensors"

# NoobAI Inpainting ControlNet
download \
    "https://huggingface.co/Acly/NoobAI-Inpainting/resolve/main/noobaiInpainting_v10.fp16.safetensors" \
    "$COMFY_DIR/models/controlnet" \
    "noobaiInpainting_v10.fp16.safetensors"

# -----------------------------------------------------------------------------
# IP-Adapter
# -----------------------------------------------------------------------------
echo ""
echo ">>> IP-Adapter models"
mkdir -p "$COMFY_DIR/models/ipadapter"

download \
    "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors" \
    "$COMFY_DIR/models/ipadapter" \
    "ip-adapter-plus_sdxl_vit-h.safetensors"

download \
    "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin" \
    "$COMFY_DIR/models/ipadapter" \
    "ip-adapter-faceid-plusv2_sdxl.bin"

# -----------------------------------------------------------------------------
# CLIP Vision
# -----------------------------------------------------------------------------
echo ""
echo ">>> CLIP Vision models"
mkdir -p "$COMFY_DIR/models/clip_vision"

download \
    "https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K/resolve/main/open_clip_pytorch_model.safetensors" \
    "$COMFY_DIR/models/clip_vision" \
    "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"

download \
    "https://huggingface.co/stabilityai/control-lora/resolve/main/revision/clip_vision_g.safetensors" \
    "$COMFY_DIR/models/clip_vision" \
    "clip_vision_g.safetensors"

# -----------------------------------------------------------------------------
# Upscale Models
# -----------------------------------------------------------------------------
echo ""
echo ">>> Upscale model: 4x_foolhardy_Remacri"
mkdir -p "$COMFY_DIR/models/upscale_models"

download \
    "https://huggingface.co/FacehugmanIII/4x_foolhardy_Remacri/resolve/main/4x_foolhardy_Remacri.pth" \
    "$COMFY_DIR/models/upscale_models" \
    "4x_foolhardy_Remacri.pth"

# -----------------------------------------------------------------------------
# SAM Models
# -----------------------------------------------------------------------------
echo ""
echo ">>> SAM model: sam_vit_b_01ec64"
mkdir -p "$COMFY_DIR/models/sams"

download \
    "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth" \
    "$COMFY_DIR/models/sams" \
    "sam_vit_b_01ec64.pth"

# -----------------------------------------------------------------------------
# Detectors (YOLO / SEG)
# -----------------------------------------------------------------------------
echo ""
echo ">>> Detector models (YOLO/SEG)"
mkdir -p "$COMFY_DIR/models/ultralytics/bbox"
mkdir -p "$COMFY_DIR/models/ultralytics/segm"

# Hands
download \
    "https://huggingface.co/Bingsu/adetailer/resolve/main/hand_yolov9c.pt" \
    "$COMFY_DIR/models/ultralytics/bbox" \
    "hand_yolov9c.pt"

# Faces
download \
    "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov9c.pt" \
    "$COMFY_DIR/models/ultralytics/bbox" \
    "face_yolov9c.pt"

# Eyes
download \
    "https://huggingface.co/GritTin/LoraStableDiffusion/resolve/c7766cc3c9b8b4f914932ce27f1cd48f25434636/Eyeful_v2-Paired.pt" \
    "$COMFY_DIR/models/ultralytics/bbox" \
    "Eyeful_v2-Paired.pt"

# NSFW detector
download \
    "https://huggingface.co/adbrasi/wanlotest/resolve/main/ntd11_anime_nsfw_segm_v5-variant1.pt" \
    "$COMFY_DIR/models/ultralytics/segm" \
    "ntd11_anime_nsfw_segm_v5-variant1.pt"

# Body segmentation
download \
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-seg.pt" \
    "$COMFY_DIR/models/ultralytics/segm" \
    "yolo11m-seg.pt"

echo ""
echo "=============================================="
echo "  All model downloads complete!"
echo "=============================================="
