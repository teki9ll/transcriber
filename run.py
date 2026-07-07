"""Entry point: starts uvicorn and opens the dashboard in the default browser."""
import threading
import time
import urllib.request
import webbrowser

import uvicorn

import config
from main import app  # noqa: F401  (triggers lifespan + model preload)


def _open_browser():
    url = f"http://{config.HOST}:{config.PORT}/api/info"
    # On first run the lifespan downloads the model (~1.5 GB) BEFORE the server
    # starts listening. Wait until the endpoint actually responds, then open the
    # browser — so the page never loads to a "connection refused" error.
    for _ in range(360):  # up to ~6 minutes
        try:
            with urllib.request.urlopen(url, timeout=1):
                break
        except Exception:
            time.sleep(1)
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


def main():
    print("=" * 60)
    print(f"  Whisper Clipboard  |  backend={config.BACKEND}")
    print(f"  device={config.DEVICE} ({config.DEVICE_NAME})")
    print(f"  Open  http://{config.HOST}:{config.PORT}")
    print("=" * 60)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
