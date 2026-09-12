#!/bin/bash
set -euo pipefail

# =============================================================================
# Startup script: Launch ComfyUI server, then start the RunPod handler
# =============================================================================

COMFY_DIR="${COMFY_DIR:-/comfyui}"

echo "[start.sh] Starting ComfyUI server..."
cd "$COMFY_DIR"

# Start ComfyUI in the background on localhost:8188
python main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --disable-auto-launch \
    --disable-metadata \
    &

COMFY_PID=$!
echo "[start.sh] ComfyUI started with PID $COMFY_PID"

# Wait for ComfyUI to be ready (poll /system_stats)
echo "[start.sh] Waiting for ComfyUI to be ready..."
MAX_WAIT=300
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1; then
        echo "[start.sh] ComfyUI is ready! (waited ${WAITED}s)"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[start.sh] ERROR: ComfyUI did not start within ${MAX_WAIT}s"
    exit 1
fi

# Start the RunPod handler
echo "[start.sh] Starting RunPod handler..."
cd /
python -u /handler.py
