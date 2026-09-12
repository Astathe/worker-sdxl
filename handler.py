"""
RunPod Serverless Handler for ComfyUI.

Accepts a full ComfyUI workflow JSON in the request, submits it to the local
ComfyUI server via its API, waits for execution, retrieves output images, and
returns them as base64-encoded PNGs (or uploads to a bucket).
"""

import os
import json
import time
import uuid
import base64
import urllib.request
import urllib.parse

import runpod
from runpod.serverless.utils import rp_upload, rp_cleanup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
COMFY_API_URL = f"http://{COMFY_HOST}"
COMFY_OUTPUT_DIR = os.environ.get("COMFY_OUTPUT_DIR", "/ComfyUI/output")
COMFY_TIMEOUT = int(os.environ.get("COMFY_TIMEOUT", "600"))  # seconds


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
    while time.time() - start < timeout:
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
        except urllib.error.URLError:
            pass  # ComfyUI may be busy
        time.sleep(2)

    raise TimeoutError(f"ComfyUI execution timed out after {timeout}s")


def collect_output_images(history_entry: dict) -> list[str]:
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
    os.makedirs(f"/{job_id}", exist_ok=True)
    image_urls = []
    for index, info in enumerate(image_infos):
        img_bytes = download_image(info)
        ext = info["filename"].rsplit(".", 1)[-1].lower() if "." in info["filename"] else "png"
        image_path = os.path.join(f"/{job_id}", f"{index}.{ext}")
        with open(image_path, "wb") as f:
            f.write(img_bytes)

        if os.environ.get("BUCKET_ENDPOINT_URL", False):
            image_url = rp_upload.upload_image(job_id, image_path)
            image_urls.append(image_url)
        else:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            image_urls.append(f"data:{mime};base64,{b64}")

    rp_cleanup.clean([f"/{job_id}"])
    return image_urls


# ---------------------------------------------------------------------------
# RunPod handler
# ---------------------------------------------------------------------------

def handler(job):
    """
    RunPod serverless handler.

    Expects job["input"] to contain:
      - "workflow": dict  — A full ComfyUI API-format workflow JSON (required)

    Returns:
      - "images": list of base64 data URIs or uploaded URLs
      - "image_url": first image URL (convenience)
    """
    job_input = job.get("input", {})
    job_id = job.get("id", str(uuid.uuid4()))

    # -----------------------------------------------------------------------
    # Validate input
    # -----------------------------------------------------------------------
    workflow = job_input.get("workflow")

    if not workflow:
        return {"error": "Missing 'workflow' in input. Provide a full ComfyUI API-format workflow JSON."}

    if isinstance(workflow, str):
        try:
            workflow = json.loads(workflow)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in 'workflow': {e}"}

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
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("[handler] Waiting for ComfyUI to start...", flush=True)
    wait_for_comfyui(timeout=300)
    print("[handler] ComfyUI is ready. Starting RunPod handler...", flush=True)
    runpod.serverless.start({"handler": handler})
