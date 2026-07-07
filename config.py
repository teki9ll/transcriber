"""Central configuration. Tweak here or override via environment variables."""
import os

# HuggingFace caches with symlinks by default, which prints a noisy warning on
# Windows without Developer Mode. Functionality is unaffected; silence the warning.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import torch

# ---------- Backend ----------
# "faster" -> faster-whisper (CTranslate2). Fastest. Best when your GPU is supported.
# "openai" -> vanilla openai/whisper (PyTorch). Most reliable on RTX 50-series
#             (Blackwell) because it uses torch's CUDA 12.8 kernels directly.
BACKEND = os.environ.get("WC_BACKEND", "faster")

# ---------- Device ----------
CUDA = torch.cuda.is_available()
DEVICE = "cuda" if CUDA else "cpu"
DEVICE_NAME = (torch.cuda.get_device_name(0) if CUDA else "CPU").strip()

# faster-whisper compute type: fp16 on GPU, int8 on CPU.
COMPUTE_TYPE = "float16" if CUDA else "int8"

# ---------- Models ----------
# canonical name -> (faster-whisper name, openai-whisper name)
MODELS = {
    "tiny":           ("tiny",           "tiny"),
    "base":           ("base",           "base"),
    "small":          ("small",          "small"),
    "medium":         ("medium",         "medium"),
    "large-v3":       ("large-v3",       "large-v3"),
    "large-v3-turbo": ("large-v3-turbo", "turbo"),
}
DEFAULT_MODEL = os.environ.get("WC_MODEL", "tiny")  # tiny = fastest first-launch download (~75 MB)

# ---------- Audio ----------
SAMPLE_RATE = 16000   # Whisper expects 16 kHz mono
CHANNELS = 1

# ---------- Optional global hotkey ----------
ENABLE_GLOBAL_HOTKEY = os.environ.get("WC_HOTKEY", "1") == "1"
GLOBAL_HOTKEY = os.environ.get("WC_HOTKEY_KEY", "f8")  # pynput key: f8, space, or a letter

# ---------- Auto-paste ----------
# After transcription + clipboard copy, simulate Ctrl+V into whatever window has
# focus. Default ON; toggleable from the dashboard. PASTE_DELAY lets the held
# push-to-talk key/modifiers release before we send Ctrl+V.
AUTO_PASTE = os.environ.get("WC_AUTO_PASTE", "1") == "1"
PASTE_DELAY = float(os.environ.get("WC_PASTE_DELAY", "0.15"))  # wait for hotkey release before pasting

# ---------- Server ----------
HOST = os.environ.get("WC_HOST", "127.0.0.1")
PORT = int(os.environ.get("WC_PORT", "8777"))
