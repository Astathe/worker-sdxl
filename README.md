# ComfyUI SDXL Worker (Advanced Gemma V38)

Run [ComfyUI](https://github.com/comfyanonymous/ComfyUI) as a serverless RunPod endpoint with pre-installed custom nodes and models for SDXL/Illustrious/NoobAI generation.

---

## Architecture

This worker runs a **ComfyUI server** internally and exposes it via a RunPod serverless handler. You submit full ComfyUI API-format workflow JSONs and receive output images.

```
┌─────────────────────────────────────────┐
│              RunPod Worker              │
│                                         │
│   ┌──────────┐     ┌───────────────┐   │
│   │  RunPod   │────▶│   ComfyUI     │   │
│   │  Handler  │◀────│   Server      │   │
│   └──────────┘     │  (port 8188)  │   │
│                     └───────────────┘   │
└─────────────────────────────────────────┘
```

## Pre-installed Custom Nodes

| Custom Node | Author |
|---|---|
| ComfyUI-Manager | Comfy-Org |
| ComfyUI-Impact-Pack | ltdrdata |
| ComfyUI-Impact-Subpack | ltdrdata |
| ComfyUI-Easy-Use | yolain |
| ComfyUI_UltimateSDUpscale | ssitu |
| rgthree-comfy | rgthree |
| ComfyUI-Image-Saver | alexopus |
| ComfyUI-KJNodes | kijai |
| ComfyUI-Lora-Manager | willmiao |
| ComfyUI-Custom-Scripts | pythongosssss |
| ComfyUI-FBCNN | Miosp |
| comfyui_controlnet_aux | Fannovel16 |
| ComfyUI_IPAdapter_plus | cubiq |
| z-tipo-extension | KohakuBlueleaf |
| ComfyUI-ppm | pamparamm |
| ComfyUI-QwenVL | 1038lab |

## Pre-installed Models

- **Checkpoint**: waiIllustriousSDXL_v170
- **LoRA**: CivitAI model 1930892
- **VAE**: sdxl_vae
- **ControlNet**: Canny, Depth, OpenPose (SDXL), NoobAI Inpainting
- **IP-Adapter**: SDXL ViT-H plus, FaceID plusv2
- **CLIP Vision**: ViT-H-14, clip_vision_g
- **Upscale**: 4x_foolhardy_Remacri
- **SAM**: sam_vit_b_01ec64
- **Detectors**: face_yolov9c, hand_yolov9c, Eyeful_v2, NSFW segm, yolo11m-seg

## Usage

Send a full ComfyUI **API-format** workflow JSON in the `workflow` field:

```json
{
  "input": {
    "workflow": {
      "3": {
        "class_type": "KSampler",
        "inputs": {
          "seed": 42,
          "steps": 25,
          "cfg": 7.0,
          "sampler_name": "euler",
          "scheduler": "normal",
          "denoise": 1.0,
          "model": ["4", 0],
          "positive": ["6", 0],
          "negative": ["7", 0],
          "latent_image": ["5", 0]
        }
      },
      "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
          "ckpt_name": "waiIllustriousSDXL_v170.safetensors"
        }
      },
      "5": {
        "class_type": "EmptyLatentImage",
        "inputs": { "width": 1024, "height": 1024, "batch_size": 1 }
      },
      "6": {
        "class_type": "CLIPTextEncode",
        "inputs": { "text": "your prompt here", "clip": ["4", 1] }
      },
      "7": {
        "class_type": "CLIPTextEncode",
        "inputs": { "text": "negative prompt", "clip": ["4", 1] }
      },
      "8": {
        "class_type": "VAEDecode",
        "inputs": { "samples": ["3", 0], "vae": ["4", 2] }
      },
      "9": {
        "class_type": "SaveImage",
        "inputs": { "filename_prefix": "ComfyUI", "images": ["8", 0] }
      }
    }
  }
}
```

> [!NOTE]
> The `workflow` must be in **ComfyUI API format** (node IDs as keys, each with `class_type` and `inputs`), not the UI-exported JSON format. You can export API-format workflows from ComfyUI by enabling "Dev Mode" in settings and clicking "Save (API Format)".

### Response

```json
{
  "output": {
    "images": [
      "data:image/png;base64,iVBORw0KGgoAAAANSUh..."
    ],
    "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUh..."
  },
  "status": "COMPLETED"
}
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `COMFY_HOST` | `127.0.0.1:8188` | ComfyUI server address |
| `COMFY_OUTPUT_DIR` | `/ComfyUI/output` | Directory where ComfyUI saves outputs |
| `COMFY_TIMEOUT` | `600` | Max seconds to wait for workflow execution |
| `BUCKET_ENDPOINT_URL` | _(none)_ | S3-compatible bucket URL for image uploads |

## Building

```bash
docker build -t comfyui-worker .
```

> [!WARNING]
> The Docker image is large (~50GB+) due to all baked-in models. Build time will be significant due to model downloads.

## Running Locally

```bash
docker run --gpus all -p 8188:8188 comfyui-worker
```
