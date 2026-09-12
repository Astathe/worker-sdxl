# Base image with CUDA 12.1
FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    ninja-build \
    git \
    wget \
    curl \
    aria2 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Set python3.11 as default
RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3

# Install pip for python3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# =============================================================================
# Install ComfyUI
# =============================================================================
WORKDIR /ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git . && \
    pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121 && \
    pip install -r requirements.txt

# =============================================================================
# Install Custom Nodes
# =============================================================================
WORKDIR /ComfyUI/custom_nodes

# ComfyUI-Manager
RUN git clone https://github.com/Comfy-Org/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-Impact-Pack
RUN git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    cd ComfyUI-Impact-Pack && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi && \
    python install.py || true

# ComfyUI-Impact-Subpack
RUN git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git && \
    cd ComfyUI-Impact-Subpack && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi && \
    python install.py || true

# ComfyUI-Easy-Use
RUN git clone https://github.com/yolain/ComfyUI-Easy-Use.git && \
    cd ComfyUI-Easy-Use && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI_UltimateSDUpscale
RUN git clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git --recursive && \
    cd ComfyUI_UltimateSDUpscale && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# rgthree-comfy
RUN git clone https://github.com/rgthree/rgthree-comfy.git && \
    cd rgthree-comfy && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-Image-Saver
RUN git clone https://github.com/alexopus/ComfyUI-Image-Saver.git && \
    cd ComfyUI-Image-Saver && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-KJNodes
RUN git clone https://github.com/kijai/ComfyUI-KJNodes.git && \
    cd ComfyUI-KJNodes && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-Lora-Manager
RUN git clone https://github.com/willmiao/ComfyUI-Lora-Manager.git && \
    cd ComfyUI-Lora-Manager && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-Custom-Scripts (pysssss)
RUN git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git && \
    cd ComfyUI-Custom-Scripts && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-FBCNN
RUN git clone https://github.com/Miosp/ComfyUI-FBCNN.git && \
    cd ComfyUI-FBCNN && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# comfyui_controlnet_aux (ControlNet Preprocessors)
RUN git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git && \
    cd comfyui_controlnet_aux && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI_IPAdapter_plus
RUN git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git && \
    cd ComfyUI_IPAdapter_plus && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# z-tipo-extension
RUN git clone https://github.com/KohakuBlueleaf/z-tipo-extension.git && \
    cd z-tipo-extension && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-ppm
RUN git clone https://github.com/pamparamm/ComfyUI-ppm.git && \
    cd ComfyUI-ppm && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI-QwenVL
RUN git clone https://github.com/1038lab/ComfyUI-QwenVL.git && \
    cd ComfyUI-QwenVL && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# ComfyUI_Mira (provides TextBoxMira node)
RUN git clone https://github.com/mirabarukaso/ComfyUI_Mira.git && \
    cd ComfyUI_Mira && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# comfyui-mixlab-nodes (provides Seed_ / CreateSeedNode node)
RUN git clone https://github.com/shadowcz007/comfyui-mixlab-nodes.git && \
    cd comfyui-mixlab-nodes && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# =============================================================================
# Install RunPod SDK
# =============================================================================
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# =============================================================================
# Download all models
# =============================================================================
COPY download_models.sh /download_models.sh
RUN chmod +x /download_models.sh && \
    COMFY_DIR=/ComfyUI /download_models.sh

# =============================================================================
# Copy handler, workflow, and startup script
# =============================================================================
WORKDIR /
COPY handler.py /handler.py
COPY start.sh /start.sh
COPY ["Advanced_Gemma_V38 UMA.json", "/workflow.json"]
COPY ["Advanced_Gemma_V38 UMA API.json", "/workflow_api.json"]
RUN chmod +x /start.sh

# =============================================================================
# Start
# =============================================================================
CMD ["/start.sh"]
