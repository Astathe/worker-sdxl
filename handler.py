"""
RunPod Serverless Handler for ComfyUI.

Supports two modes:
  1. Full workflow mode: pass a complete ComfyUI API-format workflow JSON.
  2. Simple prompt mode: pass just a prompt (and optionally negative_prompt,
     seed, width, height) — the handler injects them into the baked-in
     workflow template.
"""

import os
import json
import copy
import time
import uuid
import random
import base64
import urllib.request
import urllib.parse
import urllib.error

import runpod
from runpod.serverless.utils import rp_upload, rp_cleanup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
COMFY_API_URL = f"http://{COMFY_HOST}"
COMFY_TIMEOUT = int(os.environ.get("COMFY_TIMEOUT", "600"))  # seconds
WORKFLOW_TEMPLATE_PATH = os.environ.get("WORKFLOW_TEMPLATE_PATH", "/workflow_api.json")

# Loaded at startup
WORKFLOW_TEMPLATE = None
_INIT_DONE = False


def load_workflow_template():
    """Load the baked-in workflow template for simple prompt mode."""
    global WORKFLOW_TEMPLATE
    if os.path.exists(WORKFLOW_TEMPLATE_PATH):
        with open(WORKFLOW_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            WORKFLOW_TEMPLATE = json.load(f)
        print(f"[handler] Loaded workflow template from {WORKFLOW_TEMPLATE_PATH}", flush=True)
    else:
        print(f"[handler] WARNING: No workflow template found at {WORKFLOW_TEMPLATE_PATH}. "
              "Simple prompt mode will be unavailable.", flush=True)


def build_workflow_from_prompt(prompt, negative_prompt=None, seed=None, width=None, height=None):
    """
    Build a ComfyUI workflow by injecting simple parameters into the
    baked-in Advanced_Gemma_V38 UMA workflow template.

    Node mapping (from the API-format workflow):
      - Node "103" (TextBoxMira, title "POSITIVE"): positive prompt text
      - Node "104" (TextBoxMira, title "NEGATIVE"): negative prompt text
      - Node "99"  (Seed_): seed value
      - Node "1"   (easy int, title "Width"): width
      - Node "12"  (easy int, title "Height"): height
    """
    if WORKFLOW_TEMPLATE is None:
        raise RuntimeError(
            "No workflow template loaded. Cannot use simple prompt mode. "
            "Either provide a full 'workflow' JSON, or ensure the template "
            f"exists at {WORKFLOW_TEMPLATE_PATH}."
        )

    workflow = copy.deepcopy(WORKFLOW_TEMPLATE)

    # Validate essential nodes exist
    missing_nodes = [n for n in ["103", "104", "99", "1", "12"] if n not in workflow]
    if missing_nodes:
        raise RuntimeError(f"Workflow template is missing expected node IDs: {missing_nodes}. "
                           "Please update the node IDs in handler.py if the workflow has changed.")

    # Inject positive prompt
    if prompt is not None:
        workflow["103"]["inputs"]["text"] = prompt

    # Inject negative prompt
    if negative_prompt is not None:
        workflow["104"]["inputs"]["text"] = negative_prompt

    # Inject seed (random if not provided)
    if seed is not None:
        workflow["99"]["inputs"]["seed"] = seed
    else:
        workflow["99"]["inputs"]["seed"] = random.randint(0, 2**53 - 1)

    # Inject width
    if width is not None:
        workflow["1"]["inputs"]["value"] = width

    # Inject height
    if height is not None:
        workflow["12"]["inputs"]["value"] = height

    return workflow


# ---------------------------------------------------------------------------
# ComfyUI API helpers
# ---------------------------------------------------------------------------

def wait_for_comfyui(timeout: int = 120):
    """Block until ComfyUI is reachable."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"{COMFY_API_URL}/system_stats")
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"ComfyUI did not become available within {timeout}s")


def queue_prompt(workflow: dict, client_id: str) -> str:
    """Submit a prompt (workflow) to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY_API_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "prompt_id" not in result:
        raise RuntimeError(f"ComfyUI /prompt returned unexpected result: {result}")

    return result["prompt_id"]


def poll_history(prompt_id: str, timeout: int = COMFY_TIMEOUT) -> dict:
    """Poll /history/{prompt_id} until execution is finished."""
    start = time.time()
    attempts = 0
    while time.time() - start < timeout:
        attempts += 1
        try:
            req = urllib.request.Request(f"{COMFY_API_URL}/history/{prompt_id}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                history = json.loads(resp.read().decode("utf-8"))

            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False) or status.get("status_str") == "success":
                    return entry
                if status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI execution failed: {msgs}")
        except urllib.error.URLError as e:
            if attempts % 5 == 0:
                print(f"[handler] poll_history URLError (attempt {attempts}): {e}", flush=True)
        time.sleep(2)

    raise TimeoutError(f"ComfyUI execution timed out after {timeout}s")


def collect_output_images(history_entry: dict) -> list[dict]:
    """Extract output image filenames from a history entry."""
    images = []
    outputs = history_entry.get("outputs", {})
    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for img_info in node_output["images"]:
                filename = img_info.get("filename", "")
                subfolder = img_info.get("subfolder", "")
                img_type = img_info.get("type", "output")
                if filename:
                    images.append({
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": img_type,
                    })
    return images


def download_image(image_info: dict) -> bytes:
    """Download an image from ComfyUI /view endpoint."""
    params = urllib.parse.urlencode({
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    })
    url = f"{COMFY_API_URL}/view?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def images_to_base64(image_infos: list[dict]) -> list[str]:
    """Download images from ComfyUI and convert to base64 data URIs."""
    result = []
    for info in image_infos:
        img_bytes = download_image(info)
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        # Detect format from filename extension
        ext = info["filename"].rsplit(".", 1)[-1].lower() if "." in info["filename"] else "png"
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
        result.append(f"data:{mime};base64,{b64}")
    return result


def upload_images(image_infos: list[dict], job_id: str) -> list[str]:
    """Download images from ComfyUI and upload to bucket (if configured)."""
    workdir = f"/tmp/{job_id}"
    os.makedirs(workdir, exist_ok=True)
    image_urls = []
    for index, info in enumerate(image_infos):
        img_bytes = download_image(info)
        ext = info["filename"].rsplit(".", 1)[-1].lower() if "." in info["filename"] else "png"
        image_path = os.path.join(workdir, f"{index}.{ext}")
        with open(image_path, "wb") as f:
            f.write(img_bytes)

        bucket_endpoint = os.environ.get("BUCKET_ENDPOINT_URL", "")
        # Use bucket upload if BUCKET_ENDPOINT_URL is truthy (not empty, not "0", not "false")
        if bucket_endpoint and bucket_endpoint.lower() not in ("0", "false"):
            try:
                image_url = rp_upload.upload_image(job_id, image_path)
                image_urls.append(image_url)
            except Exception as e:
                print(f"[handler] Failed to upload to bucket: {e}. Falling back to base64.", flush=True)
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
                image_urls.append(f"data:{mime};base64,{b64}")
        else:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            image_urls.append(f"data:{mime};base64,{b64}")

    rp_cleanup.clean([workdir])
    return image_urls


# ---------------------------------------------------------------------------
# RunPod handler
# ---------------------------------------------------------------------------

def handler(job):
    """
    RunPod serverless handler.

    Supports two input modes:

    Mode 1 — Full workflow (advanced):
      {
        "input": {
          "workflow": { ... full ComfyUI API-format workflow ... }
        }
      }

    Mode 2 — Simple prompt (uses baked-in workflow template):
      {
        "input": {
          "prompt": "your positive prompt here",
          "negative_prompt": "optional negative prompt",
          "seed": 12345,
          "width": 1024,
          "height": 1536
        }
      }

    Returns:
      - "images": list of base64 data URIs or uploaded URLs
      - "image_url": first image URL (convenience)
    """
    global _INIT_DONE
    if not _INIT_DONE:
        print("[handler] Waiting for ComfyUI to start...", flush=True)
        wait_for_comfyui(timeout=300)
        print("[handler] ComfyUI is ready.", flush=True)
        load_workflow_template()
        _INIT_DONE = True

    job_input = job.get("input", {})
    job_id = job.get("id", str(uuid.uuid4()))

    # -----------------------------------------------------------------------
    # Determine mode: full workflow or simple prompt
    # -----------------------------------------------------------------------
    workflow = job_input.get("workflow")

    if workflow:
        # Mode 1: Full workflow JSON
        if isinstance(workflow, str):
            try:
                workflow = json.loads(workflow)
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in 'workflow': {e}"}
        print(f"[handler] Job {job_id}: Using full workflow mode", flush=True)
    elif job_input.get("prompt"):
        # Mode 2: Simple prompt — inject into baked-in template
        try:
            workflow = build_workflow_from_prompt(
                prompt=job_input["prompt"],
                negative_prompt=job_input.get("negative_prompt"),
                seed=job_input.get("seed"),
                width=job_input.get("width"),
                height=job_input.get("height"),
            )
            print(f"[handler] Job {job_id}: Using simple prompt mode", flush=True)
        except RuntimeError as e:
            return {"error": str(e)}
    else:
        return {
            "error": "Missing input. Provide either 'workflow' (full ComfyUI API JSON) "
                     "or 'prompt' (simple text prompt)."
        }

    # -----------------------------------------------------------------------
    # Submit to ComfyUI
    # -----------------------------------------------------------------------
    client_id = str(uuid.uuid4())

    try:
        print(f"[handler] Job {job_id}: Submitting workflow to ComfyUI...", flush=True)
        prompt_id = queue_prompt(workflow, client_id)
        print(f"[handler] Job {job_id}: prompt_id = {prompt_id}", flush=True)
    except Exception as e:
        print(f"[handler] Job {job_id}: Failed to queue prompt: {e}", flush=True)
        return {"error": f"Failed to queue prompt: {e}"}

    # -----------------------------------------------------------------------
    # Wait for completion
    # -----------------------------------------------------------------------
    try:
        print(f"[handler] Job {job_id}: Waiting for execution...", flush=True)
        history_entry = poll_history(prompt_id, timeout=COMFY_TIMEOUT)
        print(f"[handler] Job {job_id}: Execution complete!", flush=True)
    except TimeoutError as e:
        print(f"[handler] Job {job_id}: Timeout: {e}", flush=True)
        return {"error": str(e), "refresh_worker": True}
    except RuntimeError as e:
        print(f"[handler] Job {job_id}: Execution error: {e}", flush=True)
        return {"error": str(e), "refresh_worker": True}

    # -----------------------------------------------------------------------
    # Collect output images
    # -----------------------------------------------------------------------
    image_infos = collect_output_images(history_entry)

    if not image_infos:
        print(f"[handler] Job {job_id}: WARNING - No output images found!", flush=True)
        return {"error": "Workflow completed but produced no output images."}

    print(f"[handler] Job {job_id}: Found {len(image_infos)} output image(s)", flush=True)

    # -----------------------------------------------------------------------
    # Return results
    # -----------------------------------------------------------------------
    try:
        image_urls = upload_images(image_infos, job_id)
    except Exception as e:
        print(f"[handler] Job {job_id}: Error processing images: {e}", flush=True)
        return {"error": f"Error processing output images: {e}"}

    results = {
        "images": image_urls,
        "image_url": image_urls[0] if image_urls else None,
    }

    return results


# ---------------------------------------------------------------------------
# Main — must be at module level for RunPod's scanner to detect it
# ---------------------------------------------------------------------------
runpod.serverless.start({"handler": handler})
