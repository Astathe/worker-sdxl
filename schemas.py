"""
Input schema for the ComfyUI RunPod worker.

The worker accepts a full ComfyUI API-format workflow JSON.
"""

INPUT_SCHEMA = {
    'workflow': {
        'type': dict,
        'required': True,
    },
}
