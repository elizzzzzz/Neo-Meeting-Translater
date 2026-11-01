from __future__ import annotations

import os
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from meeting_interpreter.app import app


def main() -> None:
    host = os.getenv("MEETING_INTERPRETER_HOST", "127.0.0.1")
    port = int(os.getenv("MEETING_INTERPRETER_PORT", "8000"))
    server = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": host, "port": port, "log_level": "warning"},
        daemon=True,
    )
    server.start()
    health_url = f"http://{host}:{port}/health"
    for _ in range(50):
        try:
            urllib.request.urlopen(health_url, timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
    webbrowser.open(f"http://{host}:{port}")
    try:
        while server.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
