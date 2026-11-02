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


def _load_user_config() -> None:
    """Load Finder-launched app settings before importing the FastAPI app."""
    candidates = [
        Path.home() / "Library/Application Support/LocalMeetingInterpreter/.env",
        Path.home() / ".config/local-meeting-interpreter/.env",
    ]
    for config_path in candidates:
        if not config_path.is_file():
            continue
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and value and key not in os.environ:
                os.environ[key] = value
        break


_load_user_config()
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
        # Launch through LaunchServices instead of executing the browser binary
        # directly. macOS associates microphone TCC permissions with the
        # LaunchServices app identity; direct execution can make Chrome abort
        # with a missing NSMicrophoneUsageDescription error.
        subprocess.Popen(
            [
                "/usr/bin/open",
                "-na",
                str(browser_path),
                "--args",
                f"--app={url}",
                "--new-window",
                "--window-size=1440,980",
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
    app_url = f"http://{host}:{port}/?v=0.1.1"
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
