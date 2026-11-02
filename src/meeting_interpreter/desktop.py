from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSURL, NSURLRequest
from WebKit import WKWebView, WKWebViewConfiguration
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


class _NativeAppDelegate(NSObject):
    """Small native macOS shell around the local FastAPI workbench."""

    def initWithURL_(self, url: str):
        self = objc.super(_NativeAppDelegate, self).init()
        if self is not None:
            self.url = url
            self.window = None
            self.web_view = None
        return self

    def applicationDidFinishLaunching_(self, _notification):
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

        frame = NSMakeRect(0, 0, 1440, 980)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Local Meeting Interpreter")
        self.window.center()

        configuration = WKWebViewConfiguration.alloc().init()
        self.web_view = WKWebView.alloc().initWithFrame_configuration_(frame, configuration)
        self.web_view.setAutoresizingMask_(18)  # width + height
        self.window.setContentView_(self.web_view)
        self.web_view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(self.url)))
        self.window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, _application):
        return True


def _open_native_window(url: str) -> None:
    """Run the workbench in an embedded WKWebView, without launching a browser."""
    app = NSApplication.sharedApplication()
    delegate = _NativeAppDelegate.alloc().initWithURL_(url)
    app.setDelegate_(delegate)
    app.run()


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
    _open_native_window(app_url)


if __name__ == "__main__":
    main()
