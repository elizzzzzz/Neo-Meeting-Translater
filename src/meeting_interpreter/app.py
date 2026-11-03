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

from .asr import MLXWhisperBackend
from .models import AudioEvent, ErrorEvent, SessionConfig
from .pipeline import Pipeline
from .translation import OllamaTranslationBackend

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
    asr_model = os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-medium-mlx-8bit")
    translation_model = os.getenv("MEETING_INTERPRETER_OLLAMA_MODEL", "translategemma:4b") if translation_backend == "ollama" else os.getenv("MEETING_INTERPRETER_TRANSLATION_MODEL", "facebook/nllb-200-distilled-600M")
    runtime = {
        "asr_status": "loading" if mode == "local" else "mock",
        "translation_status": "loading" if mode == "local" and translation_backend == "ollama" else ("configured" if mode == "local" else "mock"),
        "asr_model": asr_model,
        "translation_backend": translation_backend,
        "translation_model": translation_model,
        "audio_frames": 0,
        "last_audio_at": None,
        "last_error": "",
        "last_translation_ms": None,
        "last_health_at": None,
        "warmup_stage": "等待启动" if mode == "local" else "演示模式",
        "warmup_message": "模型尚未预热" if mode == "local" else "可直接使用模拟字幕",
        "warmup_progress": 0 if mode == "local" else 100,
        "startup_ready": mode != "local",
        "asr_backend": None,
        "translator_backend_instance": None,
    }
    app = FastAPI(title="Local Meeting Interpreter", version="0.1.0")
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    @app.get("/health")
    async def health() -> dict[str, object]:
        ollama = {"configured": translation_backend == "ollama", "reachable": False, "model_present": None, "model_loaded": False, "loaded_models": []}
        if translation_backend == "ollama":
            try:
                def probe_ollama() -> tuple[bool, bool, bool, list[str]]:
                    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.8) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    names = {str(item.get("name", "")) for item in payload.get("models", [])}
                    loaded: list[str] = []
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=0.8) as response:
                            running = json.loads(response.read().decode("utf-8"))
                        loaded = [str(item.get("name") or item.get("model") or "") for item in running.get("models", [])]
                    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
                        pass
                    return True, translation_model in names, translation_model in loaded, loaded
                ollama["reachable"], ollama["model_present"], ollama["model_loaded"], ollama["loaded_models"] = await asyncio.to_thread(probe_ollama)
            except (OSError, urllib.error.URLError, TimeoutError, ValueError):
                pass
        runtime["last_health_at"] = time.time()
        if translation_backend == "ollama":
            if not ollama["reachable"]:
                runtime["translation_status"] = "offline"
            elif not ollama["model_present"]:
                runtime["translation_status"] = "missing"
            elif ollama["model_loaded"] and runtime["translation_status"] != "processing":
                runtime["translation_status"] = "running"
            elif runtime["translation_status"] not in {"processing", "loading"}:
                runtime["translation_status"] = "ready"
        return {"status": "ok", "mode": mode, "asr": {"status": runtime["asr_status"], "model": asr_model}, "translation": {"status": runtime["translation_status"], "backend": translation_backend, "model": translation_model, "last_response_ms": runtime["last_translation_ms"]}, "ollama": ollama, "audio": {"frames": runtime["audio_frames"], "last_audio_at": runtime["last_audio_at"]}, "models": {"stage": runtime["warmup_stage"], "message": runtime["warmup_message"], "progress": runtime["warmup_progress"], "ready": runtime["startup_ready"]}, "last_error": runtime["last_error"], "checked_at": runtime["last_health_at"]}

    @app.on_event("startup")
    async def warm_models() -> None:
        if mode != "local":
            return

        async def warm_asr() -> None:
            runtime["warmup_stage"] = "asr"
            runtime["warmup_message"] = f"正在加载语音识别模型：{asr_model}"
            runtime["warmup_progress"] = 10
            await asyncio.sleep(0)
            try:
                backend = MLXWhisperBackend(model=asr_model, language=None)
                runtime["warmup_message"] = "正在执行首次本地识别，建立热缓存…"
                runtime["warmup_progress"] = 35
                await asyncio.sleep(0)
                await backend.transcribe(b"\x00" * (16_000 * 2), 16_000, 0)
                runtime["asr_backend"] = backend
                runtime["asr_status"] = "ready"
                runtime["warmup_progress"] = 60
                runtime["warmup_message"] = "语音识别模型已就绪"
            except Exception as exc:
                runtime["asr_status"] = "error"
                runtime["warmup_stage"] = "error"
                runtime["warmup_message"] = f"语音识别模型加载失败：{exc}"
                runtime["last_error"] = str(exc)
                raise

        async def warm_translation() -> None:
            if translation_backend != "ollama":
                runtime["translation_status"] = "ready"
                runtime["warmup_progress"] = 100
                runtime["warmup_stage"] = "ready"
                runtime["warmup_message"] = "本地模型已就绪，可开始实时翻译"
                runtime["startup_ready"] = True
                return
            runtime["warmup_stage"] = "translation"
            runtime["warmup_message"] = f"正在启动 Ollama 模型：{translation_model}"
            runtime["warmup_progress"] = 70
            await asyncio.sleep(0)
            try:
                backend = OllamaTranslationBackend(model=translation_model, timeout=float(os.getenv("MEETING_INTERPRETER_OLLAMA_TIMEOUT", "300")), keep_alive=os.getenv("MEETING_INTERPRETER_OLLAMA_KEEP_ALIVE", "24h"))
                await backend.translate("测试", "zh", "ja")
                runtime["translator_backend_instance"] = backend
                runtime["translation_status"] = "ready"
                runtime["warmup_progress"] = 100
                runtime["warmup_stage"] = "ready"
                runtime["warmup_message"] = "模型已就绪，保持热启动，可开始实时翻译"
                runtime["startup_ready"] = True
            except Exception as exc:  # Surface the exact failure in the UI health panel.
                runtime["translation_status"] = "error"
                runtime["last_error"] = str(exc)
                runtime["warmup_stage"] = "error"
                runtime["warmup_message"] = f"翻译模型加载失败：{exc}"

        async def warm_all() -> None:
            try:
                await warm_asr()
                await warm_translation()
            except Exception:
                return

        asyncio.create_task(warm_all())

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
        pipeline = Pipeline(mode=mode, asr_backend=runtime.get("asr_backend"), translator_backend=runtime.get("translator_backend_instance"))
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
                        asr_backend=runtime.get("asr_backend"),
                        translator_backend=runtime.get("translator_backend_instance"),
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
                    translation_started_at = time.perf_counter()
                    if translation_backend == "ollama":
                        runtime["translation_status"] = "processing"
                    async for caption in pipeline.process_audio(event):
                        runtime["asr_status"] = "ready"
                        runtime["last_translation_ms"] = round((time.perf_counter() - translation_started_at) * 1000)
                        try:
                            await websocket.send_json(caption.model_dump(mode="json"))
                        except WebSocketDisconnect:
                            return
                    if translation_backend == "ollama" and runtime["translation_status"] == "processing":
                        runtime["translation_status"] = "running"
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
