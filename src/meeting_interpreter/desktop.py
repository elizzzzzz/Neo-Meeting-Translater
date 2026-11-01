from __future__ import annotations

import os
import platform
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from meeting_interpreter.app import app


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.15)
        return probe.connect_ex((host, port)) != 0


def _select_port(host: str, requested_port: int) -> int:
    """Avoid attaching the desktop app to an unrelated process on port 8000."""
    if _port_is_available(host, requested_port):
        return requested_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def _open_meeting_window(url: str) -> None:
    """Open the workbench as a standalone browser app when available."""
    if platform.system() != "Darwin" or os.getenv("MEETING_INTERPRETER_WINDOW_MODE", "app") == "browser":
        webbrowser.open(url)
        return

    requested_browser = os.getenv("MEETING_INTERPRETER_BROWSER", "auto").lower()
    browser_paths = {
        "chrome": [Path("/Applications/Google Chrome.app")],
        "edge": [Path("/Applications/Microsoft Edge.app")],
        "auto": [Path("/Applications/Google Chrome.app"), Path("/Applications/Microsoft Edge.app")],
    }.get(requested_browser, [])
    for browser_path in browser_paths:
        if not browser_path.exists():
            continue
        executable = browser_path / "Contents" / "MacOS" / browser_path.stem
        if not executable.exists():
            continue
        profile_dir = Path.home() / "Library" / "Application Support" / "LocalMeetingInterpreter" / "browser-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [
                str(executable),
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--window-size=1440,980",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    webbrowser.open(url)


def main() -> None:
    host = os.getenv("MEETING_INTERPRETER_HOST", "127.0.0.1")
    requested_port = int(os.getenv("MEETING_INTERPRETER_PORT", "8000"))
    port = _select_port(host, requested_port)
    if port != requested_port:
        print(f"Port {requested_port} is busy; using {port} for this session.")
    server = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": host, "port": port, "log_level": "warning"},
        daemon=True,
    )
    server.start()
    health_url = f"http://{host}:{port}/health"
    ready = False
    for _ in range(100):
        try:
            with urllib.request.urlopen(health_url, timeout=0.2) as response:
                ready = response.status == 200
            break
        except Exception:
            time.sleep(0.1)
    app_url = f"http://{host}:{port}/?v=0.1.0"
    if not ready:
        print(f"Local Meeting Interpreter server did not become ready: {health_url}")
    _open_meeting_window(app_url)
    try:
        while server.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
