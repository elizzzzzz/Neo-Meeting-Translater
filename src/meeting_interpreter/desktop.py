from __future__ import annotations

import os
import fcntl
import json
import socket
import threading
import time
import urllib.request
from collections.abc import Mapping
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivateIgnoringOtherApps,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSOpenPanel,
    NSSavePanel,
    NSModalResponseOK,
    NSColor,
    NSScreen,
    NSRunningApplication,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
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

    default_model_dir = Path.home() / "Library/Application Support/LocalMeetingInterpreter/models"
    model_dir = Path(os.environ.get("MEETING_INTERPRETER_MODEL_DIR", default_model_dir)).expanduser()
    os.environ.setdefault("MEETING_INTERPRETER_MODEL_DIR", str(model_dir))
    os.environ.setdefault("HF_HOME", str(model_dir / "huggingface"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(model_dir / "huggingface" / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(model_dir / "huggingface" / "transformers"))


_load_user_config()
from meeting_interpreter.app import app


_INSTANCE_LOCK = None


def _acquire_instance_lock() -> bool:
    """Allow only one Finder-launched app process to own the local service."""
    global _INSTANCE_LOCK
    lock_path = Path.home() / "Library/Application Support/LocalMeetingInterpreter/app.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        running = NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.localmeetinginterpreter.app")
        if running:
            running[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        return False
    _INSTANCE_LOCK = handle
    return True


class _ScriptMessageHandler(NSObject):
    """Bridge messages from the embedded workbench to the native window."""

    def initWithDelegate_(self, delegate):
        self = objc.super(_ScriptMessageHandler, self).init()
        if self is not None:
            self.delegate = delegate
        return self

    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        body = message.body()
        self.delegate.handleNativeMessage_(body)


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
            self.bridge_handler = None
            self.normal_frame = None
            self.floating = False
        return self

    def handleNativeMessage_(self, body):
        if not isinstance(body, Mapping):
            return
        message_type = body.get("type")
        if message_type == "floating":
            self.setFloating_(bool(body.get("enabled")))
        elif message_type == "choose_model_directory":
            self.chooseModelDirectory()
        elif message_type == "export_transcript":
            self.exportTranscript_(body)

    def exportTranscript_(self, body):
        panel = NSSavePanel.savePanel()
        panel.setNameFieldStringValue_(Path(str(body.get("filename") or "meeting.txt")).name)
        panel.setCanCreateDirectories_(True)
        panel.setMessage_("将会议原文和翻译保存为本地文字文件")
        if panel.runModal() != NSModalResponseOK or panel.URL() is None:
            return
        try:
            Path(panel.URL().path()).write_text(str(body.get("text") or "暂无字幕"), encoding="utf-8")
            result = {"ok": True, "message": "会议记录已保存"}
        except OSError as exc:
            result = {"ok": False, "message": f"保存失败：{exc}"}
        if self.web_view is not None:
            script = f"window.__onTranscriptExported({json.dumps(result, ensure_ascii=False)});"
            self.web_view.evaluateJavaScript_completionHandler_(script, None)

    def chooseModelDirectory(self):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setPrompt_("选择此目录")
        panel.setMessage_("选择用于保存语音识别模型缓存的本地目录；翻译模型由 Ollama 管理")
        if panel.runModal() != NSModalResponseOK or not panel.URLs():
            return
        path = panel.URLs()[0].path()
        if self.web_view is not None:
            script = f"window.__onModelDirectorySelected({json.dumps(path, ensure_ascii=False)});"
            self.web_view.evaluateJavaScript_completionHandler_(script, None)

    def setFloating_(self, enabled: bool):
        if self.window is None or self.floating == enabled:
            return
        if enabled:
            self.normal_frame = self.window.frame()
            screen = NSScreen.mainScreen()
            visible = screen.visibleFrame() if screen is not None else NSMakeRect(0, 0, 1440, 980)
            width = min(900, visible.size.width - 48)
            height = min(260, visible.size.height - 48)
            frame = NSMakeRect(visible.origin.x + 24, visible.origin.y + 24, width, height)
            self.window.setFrame_display_(frame, True)
            self.window.setLevel_(NSFloatingWindowLevel)
            self.window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary)
            self.window.setAlphaValue_(0.92)
            self.window.setOpaque_(False)
            self.window.setBackgroundColor_(NSColor.clearColor())
            self.window.setMovableByWindowBackground_(True)
            self.window.setTitle_("实时字幕浮窗")
        else:
            if self.normal_frame is not None:
                self.window.setFrame_display_(self.normal_frame, True)
            self.window.setLevel_(0)
            self.window.setCollectionBehavior_(0)
            self.window.setAlphaValue_(1.0)
            self.window.setOpaque_(True)
            self.window.setBackgroundColor_(NSColor.windowBackgroundColor())
            self.window.setTitle_("Local Meeting Interpreter")
        self.floating = enabled

    def applicationDidFinishLaunching_(self, _notification):
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

        screen = NSScreen.mainScreen()
        frame = screen.visibleFrame() if screen is not None else NSMakeRect(0, 0, 1440, 980)
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
        # visibleFrame includes the title bar; using it as a content rect alone
        # makes the resulting window taller than the available screen.
        self.window.setFrame_display_(frame, True)

        configuration = WKWebViewConfiguration.alloc().init()
        self.bridge_handler = _ScriptMessageHandler.alloc().initWithDelegate_(self)
        configuration.userContentController().addScriptMessageHandler_name_(self.bridge_handler, "native")
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
    if not _acquire_instance_lock():
        print("Local Meeting Interpreter is already running; reusing the existing app window.")
        return
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
    app_url = f"http://{host}:{port}/?v=0.2.8"
    if not ready:
        print(f"Local Meeting Interpreter server did not become ready: {health_url}")
    _open_native_window(app_url)


if __name__ == "__main__":
    main()
