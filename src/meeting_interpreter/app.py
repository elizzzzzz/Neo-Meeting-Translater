from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .asr import MLXWhisperBackend, SenseVoiceBackend, create_asr_backend, sensevoice_model_directory
from .models import AudioEvent, ErrorEvent, SessionConfig
from .pipeline import Pipeline
from .speaker import EmbeddingSpeakerBackend, speaker_model_path
from .streaming import LiveSession
from .system import current_model_directory, inspect_ollama, pull_ollama_model, read_preferences, save_preferences, save_model_directory, upgrade_ollama
from .translation import OllamaTranslationBackend

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
    asr_model = os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-medium-mlx-8bit")
    asr_engine = os.getenv('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
    if asr_engine == 'sensevoice':
        asr_model = f'SenseVoice · {sensevoice_model_directory()}'
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
        "speaker_backend": None,
        "speaker_status": "loading" if speaker_model_path().is_file() and mode == "local" else "missing",
        "speaker_message": "声纹模型尚未连接，可手动换人",
    }
    app = FastAPI(title="Local Meeting Interpreter", version="0.2.4")
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
            elif ollama["model_loaded"] and runtime["translation_status"] not in {"processing", "error"}:
                runtime["translation_status"] = "running"
            elif runtime["translation_status"] not in {"processing", "loading", "error"}:
                runtime["translation_status"] = "ready"
        return {"status": "ok", "mode": mode, "asr": {"status": runtime["asr_status"], "model": asr_model}, "speaker": {"available": runtime["speaker_backend"] is not None, "status": runtime["speaker_status"], "message": runtime["speaker_message"]}, "translation": {"status": runtime["translation_status"], "backend": translation_backend, "model": translation_model, "last_response_ms": runtime["last_translation_ms"]}, "ollama": ollama, "audio": {"frames": runtime["audio_frames"], "last_audio_at": runtime["last_audio_at"]}, "models": {"stage": runtime["warmup_stage"], "message": runtime["warmup_message"], "progress": runtime["warmup_progress"], "ready": runtime["startup_ready"]}, "settings": {"model_dir": current_model_directory()}, "last_error": runtime["last_error"], "checked_at": runtime["last_health_at"]}

    @app.get("/system/check")
    async def system_check() -> dict[str, object]:
        """Inspect local Ollama installation and recommend the default model."""
        return await asyncio.to_thread(inspect_ollama)

    @app.post("/system/upgrade")
    async def system_upgrade() -> dict[str, object]:
        """Try a Homebrew Ollama upgrade when the user explicitly requests it."""
        return await asyncio.to_thread(upgrade_ollama)

    @app.post("/system/pull-model")
    async def system_pull_model(payload: dict[str, object] | None = None) -> dict[str, object]:
        model = payload.get("model") if isinstance(payload, dict) else None
        return await asyncio.to_thread(pull_ollama_model, model if isinstance(model, str) else "translategemma:4b")

    @app.get("/settings")
    async def get_settings() -> dict[str, object]:
        return {"model_dir": current_model_directory(), "asr_engine": asr_engine,
                "sensevoice_available": all((sensevoice_model_directory() / name).is_file() for name in ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx'))}

    @app.get("/preferences")
    async def get_preferences() -> dict[str, bool]:
        return await asyncio.to_thread(read_preferences)

    @app.post("/preferences")
    async def update_preferences(payload: dict[str, object]) -> dict[str, bool]:
        try:
            return await asyncio.to_thread(save_preferences, payload.get("show_tips"))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/settings")
    async def update_settings(payload: dict[str, object]) -> dict[str, object]:
        model_dir = payload.get("model_dir")
        if not isinstance(model_dir, str) or not model_dir.strip():
            raise HTTPException(status_code=400, detail="请提供模型保存目录。")
        try:
            return await asyncio.to_thread(save_model_directory, model_dir.strip(), payload.get('asr_engine'))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
                backend = create_asr_backend()
                runtime["warmup_message"] = "正在执行首次本地识别，建立热缓存…"
                runtime["warmup_progress"] = 35
                await asyncio.sleep(0)
                if isinstance(backend, SenseVoiceBackend):
                    await asyncio.to_thread(backend.warmup)
                else:
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
                if speaker_model_path().is_file():
                    runtime["warmup_stage"] = "speaker"
                    runtime["warmup_message"] = "正在加载本地声纹模型，用于区分发言人…"
                    runtime["warmup_progress"] = 65
                    try:
                        speaker = EmbeddingSpeakerBackend()
                        await asyncio.to_thread(speaker.load)
                        runtime["speaker_backend"] = speaker
                        runtime["speaker_status"] = "ready"
                        runtime["speaker_message"] = "本地声纹已就绪 · 自动分人（测试功能）"
                    except Exception as exc:
                        runtime["speaker_status"] = "error"
                        runtime["speaker_message"] = f"声纹加载失败，可手动换人：{exc}"
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
        send_lock = asyncio.Lock()

        async def send(payload):
            async with send_lock:
                if payload['type'] == 'caption':
                    runtime['asr_status'] = 'ready'
                elif payload['type'] == 'translation_status':
                    runtime['translation_status'] = payload['state']
                    if 'last_response_ms' in payload:
                        runtime['last_translation_ms'] = payload['last_response_ms']
                elif payload['type'] == 'capture_paused':
                    runtime['asr_status'] = 'error'
                    runtime['last_error'] = payload['message']
                await websocket.send_json(payload)

        pipeline = Pipeline(mode=mode, asr_backend=runtime.get('asr_backend'), translator_backend=runtime.get('translator_backend_instance'), translate_inline=False)
        session = LiveSession(pipeline, send)
        started = False
        rejected_samples = 0
        try:
            while True:
                await asyncio.sleep(0)
                payload = json.loads(await websocket.receive_text())
                kind = payload.get('type')
                if kind == 'ping':
                    await send({'type': 'pong'})
                    continue
                if kind == 'config':
                    if started:
                        await send(ErrorEvent(message='请先停止录音再更改识别设置').model_dump(mode='json'))
                        continue
                    config = SessionConfig.model_validate(payload)
                    if config.speaker_mode == 'embedding' and runtime['speaker_backend'] is None:
                        await send(ErrorEvent(message=runtime['speaker_message']).model_dump(mode='json'))
                        continue
                    await session.close()
                    pipeline = Pipeline(source_language=config.source_language, target_language=config.target_language,
                        mode=mode, speaker_mode=config.speaker_mode, asr_backend=runtime.get('asr_backend'),
                        translator_backend=runtime.get('translator_backend_instance'), speaker_backend=runtime.get('speaker_backend'),
                        translate_inline=False)
                    session = LiveSession(pipeline, send)
                    effective_language = getattr(pipeline.asr, 'language', None) or 'auto'
                    if mode == 'local' and isinstance(pipeline.asr, SenseVoiceBackend):
                        language_name = {'zh': '中文', 'ja': '日语', 'en': '英语', 'auto': '自动识别'}.get(effective_language, effective_language)
                        await send({'type': 'status', 'stage': 'preparing', 'message': f'正在准备{language_name}识别；完成后开启收音，请稍候…'})
                        try:
                            await asyncio.to_thread(pipeline.asr.warmup)
                        except Exception as exc:
                            runtime['last_error'] = str(exc)
                            await send(ErrorEvent(message=f'所选语言准备失败，尚未开启收音：{exc}').model_dump(mode='json'))
                            continue
                    await send({'type': 'configured', 'source_language': config.source_language, 'asr_language': effective_language, 'target_language': config.target_language})
                    language_label = {'zh': '锁定中文', 'ja': '锁定日语', 'en': '锁定英语', 'auto': '自动识别'}.get(effective_language, effective_language)
                    await send({'type': 'status', 'stage': 'models', 'message': f'语音识别已配置：{language_label}；翻译模型状态：{runtime["translation_status"]}'})
                    continue
                if not started:
                    session.start()
                    started = True
                if kind == 'speaker_change':
                    session.change_speaker()
                    await send({'type': 'speaker_changed', 'message': '已标记换人，上一段音频将按顺序完整处理'})
                    continue
                if kind == 'finish':
                    try:
                        await session.finish()
                        await send({'type': 'session_finished', **session.metrics(), 'rejected_samples': rejected_samples})
                    except Exception as exc:
                        await send(ErrorEvent(message=f'收尾识别失败：{exc}').model_dump(mode='json'))
                    await websocket.close()
                    return
                try:
                    event = AudioEvent.model_validate(payload)
                    session.feed(event)
                    runtime['audio_frames'] = int(runtime['audio_frames']) + 1
                    runtime['last_audio_at'] = time.time()
                    # ACK means safely ingested, never waits for ASR or translation.
                    await send({'type': 'audio_ack', 'accepted': True, **session.metrics()})
                except (ValueError, BufferError, OSError) as exc:
                    runtime['last_error'] = str(exc)
                    if isinstance(exc, (BufferError, OSError)):
                        import base64
                        rejected_samples += len(base64.b64decode(payload.get('audio_base64', ''))) // 2
                        await send({'type': 'capture_paused', 'message': f'{exc}；最后一包未接收，本次记录可能不完整'})
                    else:
                        await send(ErrorEvent(message=str(exc)).model_dump(mode='json'))
                    await send({'type': 'audio_ack', 'accepted': False})
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            await session.close()

    return app


app = create_app()
