#!/bin/bash
set -uo pipefail

# =============================================================================
# Startup script: launch ComfyUI in the background, wait for it, start handler
# =============================================================================

COMFY_DIR="${COMFY_DIR:-/comfyui}"

# tcmalloc for better memory behaviour (same as the official worker-comfyui)
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1 || true)"
if [ -n "$TCMALLOC" ]; then export LD_PRELOAD="$TCMALLOC"; fi

# Keep ComfyUI-Manager from trying to reach the network on boot
comfy-manager-set-mode offline 2>/dev/null || echo "[start.sh] Could not set ComfyUI-Manager to offline mode" >&2

echo "[start.sh] Starting ComfyUI server..."
cd "$COMFY_DIR"
python -u main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --disable-auto-launch \
    --disable-metadata \
    --log-stdout &
COMFY_PID=$!
echo "[start.sh] ComfyUI started with PID $COMFY_PID"

# Wait for ComfyUI. The base image has no curl, so poll with Python instead.
echo "[start.sh] Waiting for ComfyUI to be ready..."
MAX_WAIT="${COMFY_STARTUP_TIMEOUT:-600}"
WAITED=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats', timeout=3)" 2>/dev/null; do
    if ! kill -0 "$COMFY_PID" 2>/dev/null; then
        echo "[start.sh] ERROR: ComfyUI process exited during startup. Check the logs above." >&2
        exit 1
    fi
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "[start.sh] ERROR: ComfyUI did not start within ${MAX_WAIT}s" >&2
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "[start.sh] ComfyUI is ready! (waited ${WAITED}s)"

echo "[start.sh] Starting RunPod handler..."
cd /
exec python -u /handler.py
