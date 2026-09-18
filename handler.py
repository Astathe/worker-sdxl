aimport runpod
import os
import copy
import random
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import urllib.error
import binascii
import subprocess
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
client_id = str(uuid.uuid4())

WAN22_WORKFLOW = "/new_Wan22_api.json"
WAN22_FLF2V_WORKFLOW = "/new_Wan22_flf2v_api.json"
DASIWA_WORKFLOW = os.getenv("DASIWA_WORKFLOW", "/DaSiWa v11 API.json")

# Node IDs in the DaSiWa v11 API workflow
DASIWA = {
    "first_image": "23",
    "last_image": "24",
    "last_image_scale": "1512:1590",
    "flf2v": "1512:1593",
    "positive": "1370",
    "negative": "1349",
    "seed": "1512:1670",
    "sampling": "1512:1671",   # steps_total, refiner_step, cfg, sampler_name, scheduler
    "seconds": "1512:1668",
    "fps": "1512:1669",
    "megapixels": "1512:1588:322",
    "lora_high": "26",
    "lora_low": "18",
    "output": "28",
}


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def to_nearest_multiple_of_16(value):
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height is not a number: {value}")
    return max(16, int(round(numeric_value / 16.0) * 16))


def download_file_from_url(url, output_path):
    result = subprocess.run(
        ["wget", "-O", output_path, "--no-verbose", "--timeout=60", url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise Exception(f"URL download failed: {result.stderr}")
    logger.info(f"Downloaded {url} -> {output_path}")
    return output_path


def save_base64_to_file(base64_data, temp_dir, output_filename):
    # Accept data URIs like "data:image/png;base64,...."
    if isinstance(base64_data, str) and base64_data.startswith("data:") and "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]
    try:
        decoded = base64.b64decode(base64_data)
    except (binascii.Error, ValueError) as e:
        raise Exception(f"Base64 decode failed: {e}")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
    with open(file_path, "wb") as f:
        f.write(decoded)
    logger.info(f"Saved base64 input to {file_path}")
    return file_path


def process_input(input_data, temp_dir, output_filename, input_type):
    if input_type == "path":
        if not os.path.exists(input_data):
            raise Exception(f"Image path does not exist: {input_data}")
        return input_data
    if input_type == "url":
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    if input_type == "base64":
        return save_base64_to_file(input_data, temp_dir, output_filename)
    raise Exception(f"Unsupported input type: {input_type}")


def get_image_input(job_input, prefix, task_id, filename):
    """Reads <prefix>_path / <prefix>_url / <prefix>_base64. Returns a local path or None."""
    for suffix, kind in (("path", "path"), ("url", "url"), ("base64", "base64")):
        key = f"{prefix}_{suffix}"
        if key in job_input and job_input[key]:
            return process_input(job_input[key], task_id, filename, kind)
    return None


# ---------------------------------------------------------------------------
# ComfyUI communication
# ---------------------------------------------------------------------------

def queue_prompt(prompt):
    url = f"http://{server_address}:8188/prompt"
    data = json.dumps({"prompt": prompt, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        # ComfyUI returns 400 with details (missing nodes, missing models, bad values)
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"ComfyUI rejected the workflow ({e.code}): {body}")


def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def get_videos(ws, prompt, output_node=None):
    prompt_id = queue_prompt(prompt)["prompt_id"]
    logger.info(f"Queued prompt {prompt_id}")

    while True:
        out = ws.recv()
        if not isinstance(out, str):
            continue
        message = json.loads(out)
        mtype = message.get("type")
        data = message.get("data", {})
        if data.get("prompt_id") not in (None, prompt_id):
            continue
        if mtype == "execution_error":
            raise Exception(
                f"ComfyUI execution error in node {data.get('node_id')} "
                f"({data.get('node_type')}): {data.get('exception_message')}"
            )
        if mtype == "execution_interrupted":
            raise Exception("ComfyUI execution was interrupted")
        if mtype == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
            break

    history = get_history(prompt_id)[prompt_id]
    outputs = history.get("outputs", {})
    node_ids = [output_node] if output_node and output_node in outputs else list(outputs.keys())

    for node_id in node_ids:
        for video in outputs[node_id].get("gifs", []):
            path = video.get("fullpath")
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8"), video.get("format", "")
    return None, None


def load_workflow(workflow_path):
    with open(workflow_path, "r") as f:
        return json.load(f)


def wait_for_comfyui():
    http_url = f"http://{server_address}:8188/"
    for attempt in range(180):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            return
        except Exception as e:
            logger.warning(f"ComfyUI not reachable yet ({attempt + 1}/180): {e}")
            time.sleep(1)
    raise Exception("Cannot connect to ComfyUI. Is it running?")


def connect_ws():
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    ws = websocket.WebSocket()
    for attempt in range(36):
        try:
            ws.connect(ws_url)
            return ws
        except Exception as e:
            logger.warning(f"WebSocket connect failed ({attempt + 1}/36): {e}")
            time.sleep(5)
    raise Exception("WebSocket connection timed out (3 min)")


# ---------------------------------------------------------------------------
# Workflow builders
# ---------------------------------------------------------------------------

def build_wan22_prompt(job_input, task_id):
    """Original behaviour of the upstream repo (unchanged API)."""
    image_path = get_image_input(job_input, "image", task_id, "input_image.jpg") or "/example_image.png"
    end_image_path = get_image_input(job_input, "end_image", task_id, "end_image.jpg")

    lora_pairs = job_input.get("lora_pairs", [])[:4]
    workflow_file = WAN22_FLF2V_WORKFLOW if end_image_path else WAN22_WORKFLOW
    prompt = load_workflow(workflow_file)

    length = job_input.get("length", 81)
    steps = job_input.get("steps", 10)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 2.0)

    prompt["244"]["inputs"]["image"] = image_path
    prompt["541"]["inputs"]["num_frames"] = length
    prompt["135"]["inputs"]["positive_prompt"] = job_input["prompt"]
    prompt["135"]["inputs"]["negative_prompt"] = job_input.get(
        "negative_prompt",
        "bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, "
        "static, overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, "
        "extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, "
        "fused fingers, still picture, messy background, three legs, many people in the background, "
        "walking backwards",
    )
    prompt["220"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["seed"] = seed
    prompt["540"]["inputs"]["cfg"] = cfg
    prompt["235"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("width", 480))
    prompt["236"]["inputs"]["value"] = to_nearest_multiple_of_16(job_input.get("height", 832))
    prompt["498"]["inputs"]["context_overlap"] = job_input.get("context_overlap", 48)
    prompt["498"]["inputs"]["context_frames"] = length

    if "834" in prompt:
        prompt["834"]["inputs"]["steps"] = steps
        prompt["829"]["inputs"]["step"] = int(steps * 0.6)

    if end_image_path:
        prompt["617"]["inputs"]["image"] = end_image_path

    for i, pair in enumerate(lora_pairs):
        if pair.get("high"):
            prompt["279"]["inputs"][f"lora_{i + 1}"] = pair["high"]
            prompt["279"]["inputs"][f"strength_{i + 1}"] = pair.get("high_weight", 1.0)
        if pair.get("low"):
            prompt["553"]["inputs"][f"lora_{i + 1}"] = pair["low"]
            prompt["553"]["inputs"][f"strength_{i + 1}"] = pair.get("low_weight", 1.0)

    return prompt, None, {"seed": seed}


def set_power_loras(node_inputs, loras):
    """Replace all LoRA slots on an rgthree Power Lora Loader node."""
    for key in [k for k in node_inputs if k.startswith("lora_")]:
        del node_inputs[key]
    for i, (name, strength) in enumerate(loras, start=1):
        node_inputs[f"lora_{i}"] = {"on": True, "lora": name, "strength": float(strength)}


def build_dasiwa_prompt(job_input, task_id):
    N = DASIWA
    prompt = load_workflow(DASIWA_WORKFLOW)

    # --- Images -----------------------------------------------------------
    image_path = get_image_input(job_input, "image", task_id, "input_image.png")
    if not image_path:
        raise Exception("DaSiWa workflow needs an image: image_path, image_url or image_base64")
    prompt[N["first_image"]]["inputs"]["image"] = image_path

    end_image_path = get_image_input(job_input, "end_image", task_id, "end_image.png")
    if not end_image_path and job_input.get("loop"):
        # Loop mode: reuse the first frame as the last frame (upload once)
        end_image_path = image_path
    if end_image_path:
        prompt[N["last_image"]]["inputs"]["image"] = end_image_path
    else:
        # Plain I2V: detach the last frame (end_image is optional on WanFirstLastFrameToVideo)
        prompt[N["flf2v"]]["inputs"].pop("end_image", None)
        prompt.pop(N["last_image_scale"], None)
        prompt.pop(N["last_image"], None)

    # --- Prompts ----------------------------------------------------------
    if not job_input.get("prompt"):
        raise Exception("'prompt' is required")
    prompt[N["positive"]]["inputs"]["text"] = job_input["prompt"]
    if "negative_prompt" in job_input:
        prompt[N["negative"]]["inputs"]["text"] = job_input["negative_prompt"]

    # --- Sampling ---------------------------------------------------------
    sampling = prompt[N["sampling"]]["inputs"]
    seed = job_input.get("seed")
    if seed is None or seed == -1:
        seed = random.randint(0, 2**48)
    prompt[N["seed"]]["inputs"]["value"] = int(seed)

    if "steps" in job_input:
        steps = int(job_input["steps"])
        if steps < 2:
            raise Exception("steps must be >= 2 (split between HIGH and LOW models)")
        sampling["steps_total"] = steps
        # Keep the workflow's HIGH/LOW split ratio (default 2 of 5) unless given explicitly
        sampling["refiner_step"] = max(1, min(steps - 1, round(steps * 0.4)))
    if "refiner_step" in job_input:
        refiner = int(job_input["refiner_step"])
        if not 1 <= refiner < sampling["steps_total"]:
            raise Exception("refiner_step must be between 1 and steps-1")
        sampling["refiner_step"] = refiner
    if "cfg" in job_input:
        sampling["cfg"] = float(job_input["cfg"])
    if "sampler_name" in job_input:
        sampling["sampler_name"] = job_input["sampler_name"]
    if "scheduler" in job_input:
        sampling["scheduler"] = job_input["scheduler"]

    # --- Length / resolution ---------------------------------------------
    # Frames = round(seconds * fps / 8) * 8 + 1 (computed inside the workflow)
    if "seconds" in job_input:
        prompt[N["seconds"]]["inputs"]["value"] = int(job_input["seconds"])
    if "fps" in job_input:
        prompt[N["fps"]]["inputs"]["value"] = float(job_input["fps"])
    # Resolution follows the input image's aspect ratio at this many megapixels (default 0.72)
    if "megapixels" in job_input:
        prompt[N["megapixels"]]["inputs"]["value"] = float(job_input["megapixels"])

    # --- LoRAs ------------------------------------------------------------
    # If lora_pairs is given it REPLACES the workflow's built-in LoRAs.
    # Pass "lora_pairs": [] to run with no LoRAs at all.
    if "lora_pairs" in job_input:
        pairs = job_input["lora_pairs"] or []
        high = [(p["high"], p.get("high_weight", 1.0)) for p in pairs if p.get("high")]
        low = [(p["low"], p.get("low_weight", 1.0)) for p in pairs if p.get("low")]
        set_power_loras(prompt[N["lora_high"]]["inputs"], high)
        set_power_loras(prompt[N["lora_low"]]["inputs"], low)

    # --- Output -----------------------------------------------------------
    out = prompt[N["output"]]["inputs"]
    out["format"] = "video/webm" if job_input.get("output_format") == "webm" else "video/h264-mp4"
    out["filename_prefix"] = f"runpod/{task_id}"

    logger.info(
        f"DaSiWa: seed={seed} steps={sampling['steps_total']} refiner={sampling['refiner_step']} "
        f"cfg={sampling['cfg']} mode={'LOOP' if end_image_path == image_path else 'FLF2V' if end_image_path else 'I2V'}"
    )
    return prompt, N["output"], {"seed": int(seed)}


WORKFLOWS = {
    "wan22": build_wan22_prompt,
    "dasiwa": build_dasiwa_prompt,
}


# ---------------------------------------------------------------------------
# RunPod handler
# ---------------------------------------------------------------------------

def handler(job):
    job_input = job.get("input", {})
    safe_log = {k: (v[:60] + "...") if isinstance(v, str) and len(v) > 200 else v for k, v in job_input.items()}
    logger.info(f"Received job input: {safe_log}")

    task_id = f"task_{uuid.uuid4()}"
    workflow_name = job_input.get("workflow", os.getenv("DEFAULT_WORKFLOW", "wan22")).lower()
    if workflow_name not in WORKFLOWS:
        return {"error": f"Unknown workflow '{workflow_name}'. Options: {list(WORKFLOWS)}"}

    try:
        prompt, output_node, meta = WORKFLOWS[workflow_name](job_input, task_id)
        wait_for_comfyui()
        ws = connect_ws()
        try:
            video_b64, fmt = get_videos(ws, prompt, output_node)
        finally:
            ws.close()
    except Exception as e:
        logger.exception("Job failed")
        return {"error": str(e)}

    if not video_b64:
        return {"error": "No video was produced."}
    return {"video": video_b64, "format": fmt, "workflow": workflow_name, **meta}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
