# Whisper Clipboard 🎙️📋

Realtime speech-to-text that **dictates whatever you say straight into whatever you're typing** — GPU-accelerated Whisper on your **RTX 5060 Ti** (Blackwell), with a live browser dashboard. Hold a hotkey (or mouse button), speak, release, and the text is transcribed, copied, and pasted for you.

---

## Introduction

Whisper Clipboard turns your voice into typed text anywhere on your PC. It runs [OpenAI Whisper](https://github.com/openai/whisper) **locally** on your NVIDIA GPU via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2), so transcription is fast and private — nothing leaves your machine.

It's built around a **push-to-talk** workflow: hold a key (or a mouse button), speak, and release. The result is sent to your clipboard and — by default — pasted directly into the focused window at your text caret, wherever you were typing. A small browser dashboard shows live audio levels, status, the latest result, and a history.

> **Typical uses:** hands-free dictation into any app — VS Code, chat, email, docs, terminals — without reaching for the keyboard.

### Features

- 🎙️ **Push-to-talk** via a global hotkey (works even when the browser isn't focused), or the on-screen button / `Space`.
- 🖱️ **Mouse buttons** can be the trigger — a thumb/side button (Mouse 4/5) is ideal, and its native action is absorbed so it only triggers dictation.
- 📋 **Auto-paste** transcribed text into the focused window (toggleable); otherwise it's copied to the clipboard for manual `Ctrl+V`.
- ⚡ **GPU-accelerated** (faster-whisper, FP16, VAD-trimmed) with a CPU fallback.
- 🔀 **Switch models on the fly** — `tiny` (fast) up to `large-v3` (most accurate).
- 🖥️ **Live web dashboard** — real-time level ring, status, result, and history.
- 🔒 **Local & private** — runs entirely on your machine.

### Platform

- **Windows** is the primary target (auto-paste and the global/mouse hotkey use Win32 APIs). Transcription itself runs cross-platform; on macOS/Linux, auto-paste and the global hotkey are unavailable, but copy-to-clipboard still works.
- **NVIDIA GPU** recommended. The project pins a CUDA 12.8 `torch` for RTX 50-series (Blackwell) support; it falls back to CPU otherwise.

---

## Setup

### 1. Prerequisites

- **NVIDIA GPU** (built and tested on the RTX 50-series / Blackwell, `sm_120`). CPU works as a fallback.
- **Python 3.10–3.12.** (3.11 works great.)
- **[uv](https://docs.astral.sh/uv/)** for environment management.

Install uv if you don't have it:

```powershell
winget install astral-sh.uv
```

### 2. Create the environment

From the project folder:

```powershell
uv sync
```

That reads `pyproject.toml`, creates `.venv`, and installs everything — including the CUDA-12.8 `torch` from PyTorch's index (configured in `pyproject.toml` under `[tool.uv.sources]`). The first run downloads a few GB (mostly torch); subsequent runs are instant.

> **Optional — system-wide hotkey** (push-to-talk that works even when the browser isn't focused):
> ```powershell
> uv sync --extra hotkey
> ```

---

## Usage

### Run it

```powershell
uv run python run.py
```

It starts the server on `http://127.0.0.1:8777` and opens the dashboard automatically. The first launch downloads the default model (**`tiny`, ~75 MB**) to your HuggingFace cache, so it's ready in well under a minute — then you can switch to a larger model from the dropdown when you want more accuracy.

### Talk

Hold the big button (or hold **Space** while the page is focused) and speak. Release → transcribed → copied → (optionally) pasted.

### Dictate from any app (global hotkey)

The browser doesn't need focus. A **system-wide hotkey** is on by default — hold it anywhere in Windows (VS Code, Office, a game, …) and speak; release → transcribed → copied to clipboard → pasted.

Customize it from the dashboard top bar:

- Click the **⌨ key** chip → press any **key combo or mouse button** (e.g. `Ctrl+Shift+D`, `Alt+F8`, `F9`, or a **mouse side button** shown as *Mouse 4* / *Mouse 5*) → it's saved instantly. Press `Esc` to cancel.
- Toggle the **switch** next to it to turn the global hotkey on/off.

> **Mouse buttons** are great for push-to-talk. A side button (*Mouse 4/5*) is the recommended choice — its native action (browser back/forward) is automatically absorbed while it's your hotkey, so it only triggers dictation. Left/right/middle are observed too, but their normal click still goes through, so pick a side button or a key combo. (No gaming-mouse software needed — but if you prefer, mapping a side button to a key in your mouse driver works via keyboard PTT too.)

### Auto-paste (paste when done)

On by default: after each transcription the text is sent to the focused window with `Ctrl+V`, landing at your text caret — wherever you were typing. Toggle it with the **paste** switch in the top bar. `Ctrl+V` is a synthetic keystroke, so it can't reach **elevated (admin)** windows unless the app itself runs elevated; normal apps (VS Code, browsers, Office, terminals) are fine.

> Tip: pick a **combo** (`Ctrl+Shift+D`) rather than a bare function key, so it doesn't collide with shortcuts in the app you're using (e.g. VS Code's `F8` = "next problem"). pynput observes keys but doesn't suppress them, so a combo avoids meaningful conflicts.

---

## How it works

```
 🎤 mic (sounddevice, 16 kHz)
   → push-to-talk: record while hotkey/mouse button held
   → Whisper on GPU (faster-whisper, FP16, VAD-trimmed)
   → text → pyperclip copies to clipboard
   → (optional) paste.py sends Ctrl+V to the focused window
   → WebSocket pushes status + live levels + result to the browser UI
```

| File | Role |
|------|------|
| `run.py` | Entry point: launches uvicorn + opens the browser |
| `main.py` | FastAPI app, WebSocket control loop, broadcast, clipboard |
| `transcriber.py` | Whisper wrapper, switchable backend, model caching |
| `audio.py` | Microphone recorder + live RMS levels |
| `hotkey.py` | Optional global push-to-talk hotkey (pynput: keys, combos, mouse buttons) |
| `paste.py` | Dependency-free Win32 `Ctrl+V` (auto-paste into focused window) |
| `config.py` | All settings (env-var overridable) |
| `static/` | Browser dashboard (HTML/CSS/JS) |

---

## Configuration (environment variables)

| Variable | Default | What it does |
|----------|---------|--------------|
| `WC_BACKEND` | `faster` | `faster` (CTranslate2, fast) or `openai` (vanilla, Blackwell-safe fallback) |
| `WC_MODEL` | `tiny` | Whisper model loaded at startup: `tiny` (fast, ~75 MB), `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`. Switchable on the fly from the UI. |
| `WC_HOST` | `127.0.0.1` | Server bind address |
| `WC_PORT` | `8777` | Server port |
| `WC_HOTKEY` | `1` | `1` (default) enables the system-wide push-to-talk hotkey at startup; `0` to start it off (still toggleable from the UI) |
| `WC_HOTKEY_KEY` | `f8` | Global hotkey key/combo or mouse button (e.g. `f8`, `space`, `ctrl+shift+d`, `mouse_x1`) |
| `WC_AUTO_PASTE` | `1` | `1` (default) auto-pastes transcribed text via `Ctrl+V` after copying; `0` = copy only. Toggleable from the dashboard. |
| `WC_PASTE_DELAY` | `0.15` | Seconds to wait after release before sending `Ctrl+V` (lets the held hotkey/modifiers release) |

Example — run on a different port with the global F8 hotkey:

```powershell
$env:WC_PORT="9000"; $env:WC_HOTKEY="1"; uv run python run.py
```

---

## ⚠️ RTX 50-series (Blackwell) notes

Your 5060 Ti uses compute capability **`sm_120`**. Two things matter:

1. **torch must be the CUDA 12.8 build.** This is handled for you in `pyproject.toml`. If you ever install torch another way and see *"no kernel image is available for execution on the device"*, you got a non-Blackwell wheel — re-run `uv sync`.

2. **CTranslate2 (faster-whisper's engine) must include `sm_120`.** Recent versions do. If faster-whisper falls back to CPU or errors about the GPU, switch to the vanilla backend:

   ```powershell
   uv pip install --no-build-isolation openai-whisper
   $env:WC_BACKEND="openai"; uv run python run.py
   ```

   `openai-whisper` uses torch's CUDA kernels directly, so it's the most reliable on brand-new GPUs.

---

## Verify the GPU is detected

```powershell
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Expect: `True NVIDIA GeForce RTX 5060 Ti` (or similar).

---

## Troubleshooting

- **Mic not capturing / silent meters** — Windows: *Settings → Privacy → Microphone* must allow apps, and select the right input device. The app uses your system default input.
- **High latency** — the default is `tiny` (fastest). Trade up to `base`, `small`, `medium`, `large-v3-turbo`, or `large-v3` for accuracy; `large-v3-turbo` is a great accuracy/speed balance on a GPU.
- **Wrong language / quality** — speech is language-auto-detected. Speak clearly; VAD trims silence automatically.
- **Port in use** — set `WC_PORT` to something else.

---

## License

MIT — see [LICENSE](LICENSE). © 2026 Tejas Solanke.
