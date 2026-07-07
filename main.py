"""FastAPI backend: WebSocket control loop, push-to-talk recording, transcription,
clipboard copy, and live status/level broadcast to the browser UI.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pyperclip
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
from audio import AudioRecorder
from paste import paste_clipboard
from transcriber import Transcriber

# ---- module-level state (populated in lifespan) ----
loop = None                  # running event loop (for cross-thread scheduling)
clients: dict = {}           # WebSocket -> asyncio.Queue (outbound)
transcriber = Transcriber()
recorder: AudioRecorder = None
hotkey_listener = None
status = "loading"
auto_paste = config.AUTO_PASTE


def set_status(s: str):
    global status
    status = s
    broadcast({"type": "status", "state": s})


def broadcast(msg: dict):
    """Thread-safe fan-out to every connected client's outbound queue."""
    if loop is None:
        return
    for q in list(clients.values()):
        try:
            loop.call_soon_threadsafe(q.put_nowait, msg)
        except RuntimeError:
            pass


# ---- push-to-talk control (async coroutines) ----
async def do_start():
    if recorder.is_recording or status in ("transcribing", "loading"):
        return
    set_status("recording")
    recorder.start()


async def do_stop():
    if not recorder.is_recording:
        return
    audio = recorder.stop()
    set_status("transcribing")
    t0 = time.perf_counter()
    text = await loop.run_in_executor(None, transcriber.transcribe, audio)
    elapsed = time.perf_counter() - t0
    text = (text or "").strip()

    copied = False
    if text:
        try:
            pyperclip.copy(text)
            copied = True
        except Exception as e:
            broadcast({"type": "error", "message": f"Clipboard copy failed: {e}"})

    pasted = False
    if copied and auto_paste:
        def _do_paste():
            time.sleep(config.PASTE_DELAY)   # let the held hotkey/modifiers release
            return paste_clipboard()
        pasted = await loop.run_in_executor(None, _do_paste)

    broadcast({
        "type": "result",
        "text": text,
        "copied": copied,
        "pasted": pasted,
        "elapsed": round(elapsed, 3),
        "model": transcriber.current,
    })
    set_status("idle")


async def do_set_model(name: str):
    set_status("loading")
    await loop.run_in_executor(None, transcriber.load, name)
    broadcast({"type": "model_changed", "model": transcriber.current})
    set_status("idle")


# ---- app lifecycle ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop, recorder, hotkey_listener
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, transcriber.load, config.DEFAULT_MODEL)
    recorder = AudioRecorder(on_level=lambda rms: broadcast({"type": "level", "rms": rms}))

    try:
        from hotkey import HotkeyListener, is_available
        if is_available():
            hotkey_listener = HotkeyListener(
                loop, do_start, do_stop, config.GLOBAL_HOTKEY,
                enabled=config.ENABLE_GLOBAL_HOTKEY,
            )
            hotkey_listener.start()
            print(f"[hotkey] global push-to-talk: key='{config.GLOBAL_HOTKEY}' enabled={config.ENABLE_GLOBAL_HOTKEY}")
        else:
            print("[hotkey] pynput not installed (uv sync --extra hotkey) — UI hotkey disabled")
    except Exception as e:
        print(f"[hotkey] unavailable: {e}")
        hotkey_listener = None

    print(f"[ready] backend={config.BACKEND} device={config.DEVICE} ({config.DEVICE_NAME})")
    set_status("idle")
    yield


app = FastAPI(lifespan=lifespan)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def api_info():
    return {
        "device": config.DEVICE,
        "device_name": config.DEVICE_NAME,
        "cuda": config.CUDA,
        "backend": config.BACKEND,
        "models": list(config.MODELS.keys()),
        "current_model": transcriber.current,
        "global_hotkey": config.ENABLE_GLOBAL_HOTKEY,
        "hotkey_key": config.GLOBAL_HOTKEY,
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global auto_paste
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    clients[ws] = q

    await ws.send_json({
        "type": "info",
        "device": config.DEVICE,
        "device_name": config.DEVICE_NAME,
        "cuda": config.CUDA,
        "backend": config.BACKEND,
        "global_hotkey": config.ENABLE_GLOBAL_HOTKEY,
        "hotkey_key": config.GLOBAL_HOTKEY,
    })
    await ws.send_json({"type": "models", "models": list(config.MODELS.keys()), "current": transcriber.current})
    await ws.send_json({"type": "status", "state": status})
    hk = hotkey_listener.state() if hotkey_listener else {"enabled": False, "key": None}
    await ws.send_json({"type": "hotkey", "enabled": hk["enabled"], "key": hk["key"],
                        "available": hotkey_listener is not None})
    await ws.send_json({"type": "auto_paste", "enabled": auto_paste})

    async def sender():
        while True:
            msg = await q.get()
            try:
                await ws.send_json(msg)
            except Exception:
                return

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "start":
                await do_start()
            elif action == "stop":
                await do_stop()
            elif action == "set_model":
                await do_set_model(msg.get("model"))
            elif action == "set_hotkey":
                key = (msg.get("key") or "").strip()
                if hotkey_listener is not None and key:
                    hotkey_listener.reconfigure(key)
                    s = hotkey_listener.state()
                    broadcast({"type": "hotkey", "enabled": s["enabled"], "key": s["key"], "available": True})
            elif action == "set_hotkey_enabled":
                if hotkey_listener is not None:
                    hotkey_listener.set_enabled(bool(msg.get("enabled")))
                    s = hotkey_listener.state()
                    broadcast({"type": "hotkey", "enabled": s["enabled"], "key": s["key"], "available": True})
            elif action == "set_auto_paste":
                auto_paste = bool(msg.get("enabled"))
                broadcast({"type": "auto_paste", "enabled": auto_paste})
    except WebSocketDisconnect:
        pass
    finally:
        clients.pop(ws, None)
        sender_task.cancel()
