from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import AudioEvent, ErrorEvent, SessionConfig
from .pipeline import Pipeline
from .translation import OllamaTranslationBackend

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
    asr_model = os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-small-mlx-8bit")
    translation_model = os.getenv("MEETING_INTERPRETER_OLLAMA_MODEL", "translategemma:4b") if translation_backend == "ollama" else os.getenv("MEETING_INTERPRETER_TRANSLATION_MODEL", "facebook/nllb-200-distilled-600M")
    runtime = {
        "asr_status": "configured" if mode == "local" else "mock",
        "translation_status": "loading" if mode == "local" and translation_backend == "ollama" else ("configured" if mode == "local" else "mock"),
        "asr_model": asr_model,
        "translation_backend": translation_backend,
        "translation_model": translation_model,
        "audio_frames": 0,
        "last_audio_at": None,
        "last_error": "",
    }
    app = FastAPI(title="Local Meeting Interpreter", version="0.1.0")
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    @app.get("/health")
    async def health() -> dict[str, object]:
        ollama = {"configured": translation_backend == "ollama", "reachable": False, "model_present": None}
        if translation_backend == "ollama":
            try:
                def probe_ollama() -> tuple[bool, bool]:
                    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.8) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    names = {str(item.get("name", "")) for item in payload.get("models", [])}
                    return True, translation_model in names
                ollama["reachable"], ollama["model_present"] = await asyncio.to_thread(probe_ollama)
            except (OSError, urllib.error.URLError, TimeoutError, ValueError):
                pass
        return {"status": "ok", "mode": mode, "asr": {"status": runtime["asr_status"], "model": asr_model}, "translation": {"status": runtime["translation_status"], "backend": translation_backend, "model": translation_model}, "ollama": ollama, "audio": {"frames": runtime["audio_frames"], "last_audio_at": runtime["last_audio_at"]}, "last_error": runtime["last_error"]}

    @app.on_event("startup")
    async def warm_models() -> None:
        if mode != "local" or translation_backend != "ollama":
            return

        async def warm_translation() -> None:
            try:
                backend = OllamaTranslationBackend(model=translation_model, timeout=float(os.getenv("MEETING_INTERPRETER_OLLAMA_TIMEOUT", "300")), keep_alive=os.getenv("MEETING_INTERPRETER_OLLAMA_KEEP_ALIVE", "30m"))
                await backend.translate("测试", "zh", "ja")
                runtime["translation_status"] = "ready"
            except Exception as exc:  # Surface the exact failure in the UI health panel.
                runtime["translation_status"] = "error"
                runtime["last_error"] = str(exc)

        asyncio.create_task(warm_translation())

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            WEB_DIR / "index.html",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "status", "stage": "service", "message": f"本地服务已连接；ASR：{asr_model}；翻译：{translation_model}"})
        pipeline = Pipeline(mode=mode)
        try:
            while True:
                payload = json.loads(await websocket.receive_text())
                if payload.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                if payload.get("type") == "config":
                    config = SessionConfig.model_validate(payload)
                    pipeline = Pipeline(
                        source_language=config.source_language,
                        target_language=config.target_language,
                        mode=mode,
                        speaker_mode=config.speaker_mode,
                    )
                    await websocket.send_json({"type": "configured", "target_language": config.target_language})
                    await websocket.send_json({"type": "status", "stage": "models", "message": f"ASR 已配置：{asr_model}；翻译模型状态：{runtime['translation_status']}"})
                    continue
                try:
                    event = AudioEvent.model_validate(payload)
                    runtime["audio_frames"] = int(runtime["audio_frames"]) + 1
                    runtime["last_audio_at"] = time.time()
                    if int(runtime["audio_frames"]) == 1 or int(runtime["audio_frames"]) % 20 == 0:
                        await websocket.send_json({"type": "status", "stage": "audio", "message": f"已收到音频帧：{runtime['audio_frames']}"})
                    async for caption in pipeline.process_audio(event):
                        runtime["asr_status"] = "ready"
                        try:
                            await websocket.send_json(caption.model_dump(mode="json"))
                        except WebSocketDisconnect:
                            return
                except Exception as exc:  # Surface errors to the UI without dropping the session.
                    runtime["last_error"] = str(exc)
                    if "Ollama" in str(exc) or "翻译" in str(exc):
                        runtime["translation_status"] = "error"
                    else:
                        runtime["asr_status"] = "error"
                    try:
                        await websocket.send_json({"type": "status", "stage": "error", "message": str(exc)})
                        await websocket.send_json(ErrorEvent(message=str(exc)).model_dump(mode="json"))
                    except WebSocketDisconnect:
                        return
        except WebSocketDisconnect:
            return

    return app


app = create_app()
