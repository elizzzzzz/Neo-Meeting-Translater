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

from .asr import AppleSpeechBackend, MLXWhisperBackend, SenseVoiceBackend, ServiceASRBackend, create_asr_backend, sensevoice_model_directory
from .local_services import SERVICE_URLS, SERVICE_NAMES, inspect_service, local_url
from .models import AudioEvent, ErrorEvent, SessionConfig
from .pipeline import Pipeline
from .speaker import EmbeddingSpeakerBackend, speaker_model_path
from .streaming import LiveSession
from .system import current_model_directory, download_asr_model, inspect_asr_models, inspect_ollama, install_ollama, load_user_config, model_settings, pull_ollama_model, read_preferences, save_preferences, save_model_directory, upgrade_ollama
from .translation import create_translation_backend

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    def read_model_options():
        translation_backend = os.getenv("MEETING_INTERPRETER_TRANSLATION_BACKEND", "nllb").lower()
        asr_model = os.getenv("MEETING_INTERPRETER_ASR_MODEL", "mlx-community/whisper-medium-mlx-8bit")
        asr_engine = os.getenv('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
        if asr_engine == 'apple':
            asr_model = 'Apple SpeechAnalyzer · Apple 本机语音识别'
        elif asr_engine == 'sensevoice':
            asr_model = f'SenseVoice · {sensevoice_model_directory()}'
        elif asr_engine in SERVICE_URLS:
            asr_model = os.getenv('MEETING_INTERPRETER_SERVICE_ASR_MODEL', '')
        translation_model = os.getenv("MEETING_INTERPRETER_OLLAMA_MODEL", "translategemma:4b") if translation_backend == "ollama" else os.getenv("MEETING_INTERPRETER_TRANSLATION_MODEL", "facebook/nllb-200-distilled-600M")
        if translation_backend in SERVICE_URLS and translation_backend != 'ollama':
            translation_model = os.getenv(f'MEETING_INTERPRETER_{translation_backend.upper()}_MODEL', '')
        translation_url = os.getenv(f'MEETING_INTERPRETER_{translation_backend.upper()}_URL', SERVICE_URLS.get(translation_backend, ''))
        asr_url = os.getenv('MEETING_INTERPRETER_ASR_URL', SERVICE_URLS.get(asr_engine, ''))
        return translation_backend, asr_model, asr_engine, translation_model, translation_url, asr_url

    translation_backend, asr_model, asr_engine, translation_model, translation_url, asr_url = read_model_options()
    runtime = {
        "asr_status": "loading" if mode == "local" else "mock",
        "translation_status": "loading" if mode == "local" and translation_backend in SERVICE_URLS else ("configured" if mode == "local" else "mock"),
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
        "applying": False, "revision": 0, "requested_revision": 0, "generation": 0,
        "asr_backend": None,
        "translator_backend_instance": None,
        "speaker_backend": None,
        "speaker_status": "loading" if speaker_model_path().is_file() and mode == "local" else "missing",
        "speaker_message": "声纹模型尚未连接，可手动换人",
    }
    settings_lock = asyncio.Lock()
    connections = {}
    cleanup_tasks = set()
    runtime["options"] = read_model_options()
    app = FastAPI(title="NMT · Neo Meeting Translater", version="0.2.18")
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    @app.get("/health")
    async def health() -> dict[str, object]:
        generation = runtime['generation']
        translation_backend, asr_model, asr_engine, translation_model, translation_url, asr_url = runtime['options']
        translation_status, asr_status = runtime['translation_status'], runtime['asr_status']
        ollama = {"configured": translation_backend == "ollama", "reachable": False, "model_present": None, "model_loaded": False, "loaded_models": []}
        if translation_backend == "ollama":
            try:
                def probe_ollama() -> tuple[bool, bool, bool, list[str]]:
                    with urllib.request.urlopen(f"{translation_url}/api/tags", timeout=0.8) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    names = {str(item.get("name", "")) for item in payload.get("models", [])}
                    loaded: list[str] = []
                    try:
                        with urllib.request.urlopen(f"{translation_url}/api/ps", timeout=0.8) as response:
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
                translation_status = "offline"
            elif not ollama["model_present"]:
                translation_status = "missing"
            elif ollama["model_loaded"] and translation_status not in {"processing", "error"}:
                translation_status = "running"
            elif translation_status not in {"processing", "loading", "error"}:
                translation_status = "ready"
        translation_service = dict(ollama, provider=translation_backend, name=SERVICE_NAMES.get(translation_backend, '内置翻译'))
        if translation_backend in SERVICE_URLS and translation_backend != 'ollama':
            translation_service = await asyncio.to_thread(inspect_service, translation_backend, translation_url, .8)
            translation_service['model_present'] = any(m['id'] == translation_model for m in translation_service['models'])
            if not translation_service['reachable']:
                translation_status = 'offline'
            elif not translation_service['model_present']:
                translation_status = 'missing'
        connected = runtime['startup_ready']
        if translation_backend in SERVICE_URLS:
            connected = connected and translation_service['reachable'] and translation_service['model_present']
        asr_service = None
        if asr_engine in SERVICE_URLS:
            asr_service = await asyncio.to_thread(inspect_service, asr_engine, asr_url, .8)
            present = any(m['id'] == asr_model for m in asr_service['models'])
            connected = connected and asr_service['reachable'] and present
            if not asr_service['reachable'] or not present:
                asr_status = 'offline' if not asr_service['reachable'] else 'missing'
        if generation != runtime['generation']:
            return await health()
        applying = runtime['applying']
        settings_state = {**model_settings(), 'restart_required': False, 'applying': applying,
                          'revision': runtime['revision'], 'requested_revision': runtime['requested_revision']}
        connected = connected and not applying
        model_state = {'stage': 'applying' if applying else runtime['warmup_stage'],
                       'message': (runtime['warmup_message'] if runtime.get('apply_phase') == 'loading' else runtime['apply_message']) if applying else runtime['warmup_message'] if connected or not runtime['startup_ready'] else '所选模型服务已断开或模型不可用，请检查本地设置。',
                       'progress': 0 if applying and runtime.get('apply_phase') != 'loading' else runtime['warmup_progress'], 'ready': bool(connected)}
        return {"status": "ok", "mode": mode, "asr": {"status": asr_status, "model": asr_model, 'backend': asr_engine, 'service': asr_service}, "speaker": {"available": runtime["speaker_backend"] is not None, "status": runtime["speaker_status"], "message": runtime["speaker_message"]}, "translation": {"status": translation_status, "backend": translation_backend, "model": translation_model, "last_response_ms": runtime["last_translation_ms"], 'service': translation_service}, "ollama": ollama, "audio": {"frames": runtime["audio_frames"], "last_audio_at": runtime["last_audio_at"]}, "models": model_state, "settings": settings_state, "last_error": '' if applying else runtime['last_error'], "checked_at": runtime["last_health_at"]}

    @app.get("/system/check")
    async def system_check() -> dict[str, object]:
        """Inspect local Ollama installation and recommend the default model."""
        return await asyncio.to_thread(inspect_ollama)

    @app.post("/system/upgrade")
    async def system_upgrade() -> dict[str, object]:
        """Try a Homebrew Ollama upgrade when the user explicitly requests it."""
        return await asyncio.to_thread(upgrade_ollama)

    @app.post("/system/install")
    async def system_install() -> dict[str, object]:
        """Install Ollama after an explicit user action in local settings."""
        return await asyncio.to_thread(install_ollama)

    @app.post("/system/pull-model")
    async def system_pull_model(payload: dict[str, object] | None = None) -> dict[str, object]:
        model = payload.get("model") if isinstance(payload, dict) else None
        return await asyncio.to_thread(pull_ollama_model, model if isinstance(model, str) else "translategemma:4b")

    @app.get("/system/models")
    async def system_models(engine: str = "whisper", model: str | None = None, model_dir: str | None = None, language_pair: str | None = None) -> dict[str, object]:
        try:
            if engine == "apple":
                if language_pair not in (None, "zh-ja", "zh-en", "en-ja"):
                    raise ValueError("请选择中日、中英或英日会议语言")
                return await asyncio.to_thread(inspect_asr_models, "apple", languages=language_pair.split("-") if language_pair else None)
            return await asyncio.to_thread(inspect_asr_models, engine if engine in {"whisper", "sensevoice", 'nllb'} else "whisper", model, model_dir)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/system/download-asr")
    async def system_download_asr(payload: dict[str, object] | None = None) -> dict[str, object]:
        engine = payload.get("engine") if isinstance(payload, dict) else "whisper"
        model = payload.get('model') if isinstance(payload, dict) else None
        if engine == 'apple':
            languages = payload.get('languages') if isinstance(payload, dict) else None
            if not isinstance(languages, list) or not languages or not all(isinstance(item, str) and item in {'zh', 'ja', 'en'} for item in languages) or len(languages) > 3:
                raise HTTPException(status_code=400, detail='请选择需要准备的中文、日语或英语语言资源')
            return await asyncio.to_thread(download_asr_model, 'apple', languages=languages)
        return await asyncio.to_thread(download_asr_model, engine if isinstance(engine, str) else "whisper", model=model if isinstance(model, str) else None)

    @app.get("/settings")
    async def get_settings() -> dict[str, object]:
        return {**model_settings(),
                "sensevoice_available": inspect_asr_models('sensevoice')['installed']}

    @app.get('/services/models')
    async def service_models(provider: str = 'ollama', url: str | None = None):
        try:
            return await asyncio.to_thread(inspect_service, provider, url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/preferences")
    async def get_preferences() -> dict[str, object]:
        return await asyncio.to_thread(read_preferences)

    @app.post("/preferences")
    async def update_preferences(payload: dict[str, object]) -> dict[str, object]:
        try:
            return await asyncio.to_thread(save_preferences, payload.get("show_tips"), payload.get('interface_language'))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/settings")
    async def update_settings(payload: dict[str, object]) -> dict[str, object]:
        model_dir = payload.get("model_dir")
        if not isinstance(model_dir, str) or not model_dir.strip():
            raise HTTPException(status_code=400, detail="请提供模型保存目录。")
        async with settings_lock:
            try:
                selection = {key: payload[key] for key in ('asr_model', 'asr_url', 'translation_backend', 'translation_model', 'translation_url') if key in payload}
                result = await asyncio.to_thread(save_model_directory, model_dir.strip(), payload.get('asr_engine'), selection)
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            runtime['requested_revision'] += 1
            runtime.update(applying=True, apply_phase='draining', startup_ready=False, apply_message='设置已保存，正在应用模型配置…')
            if runtime.get('apply_task') is None or runtime['apply_task'].done():
                runtime['apply_task'] = asyncio.create_task(apply_saved_settings())
            return {**result, 'restart_required': False, 'applying': True, 'revision': runtime['requested_revision']}

    async def release_models():
        backend = runtime.get('asr_backend')
        if isinstance(backend, AppleSpeechBackend):
            await asyncio.to_thread(backend.client.close)
        runtime.update(asr_backend=None, translator_backend_instance=None, speaker_backend=None)
        # All native work has drained before releasing process-global MLX weights.
        # Avoid importing an unused engine just to clear its cache.
        def collect():
            import gc
            module = sys.modules.get('mlx_whisper.transcribe')
            holder = getattr(module, 'ModelHolder', None)
            if holder is not None:
                holder.model = holder.model_path = None
            gc.collect()
        await asyncio.to_thread(collect)

    async def apply_saved_settings():
        nonlocal translation_backend, asr_model, asr_engine, translation_model, translation_url, asr_url
        try:
            # Clients normally finish accepted audio before POSTing settings.
            # Retire any other open client and await its native jobs as well.
            for websocket, (done, retire) in list(connections.items()):
                retire.set()
                try:
                    await websocket.send_json({'type': 'settings_applying', 'message': '正在应用新模型，收音暂停；已显示的发言记录保留。'})
                    await websocket.close(code=1012)
                except (RuntimeError, WebSocketDisconnect):
                    pass
                await done.wait()
            while runtime['revision'] < runtime['requested_revision']:
                previous = runtime.get('warmup_task')
                if previous is not None and not previous.done():
                    runtime['apply_message'] = '正在等待当前模型操作结束，随后自动应用新设置…'
                    # Cancelling a Python await cannot stop a native GPU/thread job.
                    await asyncio.shield(previous)
                revision = runtime['requested_revision']
                runtime['apply_phase'] = 'draining'
                runtime['apply_message'] = '正在释放旧模型并应用最新设置…'
                await release_models()
                await asyncio.to_thread(load_user_config)
                translation_backend, asr_model, asr_engine, translation_model, translation_url, asr_url = read_model_options()
                runtime['options'] = read_model_options()
                runtime['generation'] += 1
                runtime.update(asr_model=asr_model, translation_backend=translation_backend, translation_model=translation_model,
                               startup_ready=False, asr_status='loading', translation_status='loading', last_error='',
                               last_translation_ms=None, warmup_progress=0, warmup_stage='applying',
                               speaker_status='missing', speaker_message='声纹模型尚未连接，可手动换人')
                runtime['apply_phase'] = 'loading'
                runtime['apply_message'] = '设置已应用，正在加载所选模型…'
                await warm_models()
                if mode == 'local':
                    await asyncio.shield(runtime['warmup_task'])
                else:
                    runtime.update(startup_ready=True, warmup_stage='ready', warmup_progress=100,
                                   warmup_message='设置已生效', asr_status='mock', translation_status='mock')
                runtime['revision'] = revision
            runtime['applying'] = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            runtime.update(applying=False, startup_ready=False, warmup_stage='error', last_error=str(exc),
                           warmup_message=f'设置已保存，应用失败：{exc}', revision=runtime['requested_revision'])

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
                runtime["asr_backend"] = backend
                runtime["warmup_message"] = "正在执行首次本地识别，建立热缓存…"
                runtime["warmup_progress"] = 35
                await asyncio.sleep(0)
                if isinstance(backend, AppleSpeechBackend):
                    await backend.warmup(initial=True)
                elif isinstance(backend, ServiceASRBackend):
                    await backend.warmup()
                elif isinstance(backend, SenseVoiceBackend):
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
            if translation_backend not in SERVICE_URLS:
                runtime["translator_backend_instance"] = create_translation_backend()
                runtime["translation_status"] = "ready"
                runtime["warmup_progress"] = 100
                runtime["warmup_stage"] = "ready"
                runtime["warmup_message"] = "本地模型已就绪，可开始实时翻译"
                runtime["startup_ready"] = True
                return
            runtime["warmup_stage"] = "translation"
            runtime["warmup_message"] = f"正在启动 {SERVICE_NAMES[translation_backend]} 翻译模型：{translation_model}"
            runtime["warmup_progress"] = 70
            await asyncio.sleep(0)
            try:
                backend = create_translation_backend()
                backend.timeout = float(os.getenv(f'MEETING_INTERPRETER_{translation_backend.upper()}_TIMEOUT', '300'))
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
                if asr_engine == translation_backend == 'llama' and asr_model != translation_model and local_url(asr_url) == local_url(translation_url):
                    service = await asyncio.to_thread(inspect_service, 'llama', asr_url)
                    if service.get('max_loaded_models', 2) < 2:
                        runtime.update(warmup_stage='error', asr_status='error', translation_status='error',
                            warmup_message='llama.app 当前仅能驻留 1 个模型。请把识别与翻译分配到不同服务，或在 llama.app 允许两个模型同时运行。')
                        return
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

        runtime['warmup_task'] = asyncio.create_task(warm_all())

    @app.on_event("shutdown")
    async def stop_native_speech() -> None:
        apply_task = runtime.get('apply_task')
        if apply_task is not None and not apply_task.done():
            apply_task.cancel()
            await asyncio.gather(apply_task, return_exceptions=True)
        task = runtime.get('warmup_task')
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        backend = runtime.get('asr_backend')
        if isinstance(backend, AppleSpeechBackend):
            await asyncio.to_thread(backend.client.close)

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
        if runtime['applying']:
            await websocket.send_json({'type':'error', 'message':'模型设置正在自动应用，请等待模型就绪后开始录音。'})
            await websocket.close(code=1008)
            return
        done = asyncio.Event()
        await websocket.send_json({"type": "status", "stage": "service", "message": f"本地服务已连接；ASR：{asr_model}；翻译：{translation_model}"})
        if runtime['applying']:
            await websocket.close(code=1012)
            return
        send_lock = asyncio.Lock()

        async def send(payload):
            async with send_lock:
                if runtime['applying']:
                    return
                if payload['type'] == 'caption':
                    runtime['asr_status'] = 'ready'
                elif payload['type'] == 'translation_status':
                    runtime['translation_status'] = payload['state']
                    if 'last_response_ms' in payload:
                        runtime['last_translation_ms'] = payload['last_response_ms']
                elif payload['type'] == 'capture_paused':
                    runtime['asr_status'] = 'error'
                    runtime['last_error'] = payload['message']
                elif payload['type'] == 'segment_skipped':
                    if payload['stage'] == 'translation':
                        runtime['translation_status'] = 'timeout'
                    else:
                        runtime['asr_status'] = 'timeout'
                await websocket.send_json(payload)

        pipeline = Pipeline(mode=mode, asr_backend=runtime.get('asr_backend'), translator_backend=runtime.get('translator_backend_instance'), translate_inline=False)
        session = LiveSession(pipeline, send)
        retire = asyncio.Event()
        connections[websocket] = (done, retire)
        started = False
        rejected_samples = 0
        try:
            while True:
                await asyncio.sleep(0)
                if retire.is_set():
                    return
                receiving = asyncio.create_task(websocket.receive_text())
                retiring = asyncio.create_task(retire.wait())
                try:
                    await asyncio.wait((receiving, retiring), return_when=asyncio.FIRST_COMPLETED)
                    if retire.is_set():
                        return
                    payload = json.loads(receiving.result())
                finally:
                    for pending in (receiving, retiring):
                        if not pending.done():
                            pending.cancel()
                    await asyncio.gather(receiving, retiring, return_exceptions=True)
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
                        language_pair=config.language_pair,
                        mode=mode, speaker_mode=config.speaker_mode, asr_backend=runtime.get('asr_backend'),
                        translator_backend=runtime.get('translator_backend_instance'), speaker_backend=runtime.get('speaker_backend'),
                        translate_inline=False)
                    session = LiveSession(pipeline, send)
                    effective_language = getattr(pipeline.asr, 'language', None) or 'auto'
                    if mode == 'local' and isinstance(pipeline.asr, AppleSpeechBackend):
                        await send({'type': 'status', 'stage': 'preparing', 'message': '正在准备 Apple 本机语音识别…'})
                        try:
                            await pipeline.asr.warmup()
                        except Exception as exc:
                            await send(ErrorEvent(message=f'Apple 识别尚未就绪，未开启收音：{exc}').model_dump(mode='json'))
                            continue
                    if mode == 'local' and isinstance(pipeline.asr, SenseVoiceBackend):
                        language_name = {'zh': '中文', 'ja': '日语', 'en': '英语', 'auto': '自动识别'}.get(effective_language, effective_language)
                        await send({'type': 'status', 'stage': 'preparing', 'message': f'正在准备{language_name}识别；完成后开启收音，请稍候…'})
                        try:
                            await asyncio.to_thread(pipeline.asr.warmup)
                        except Exception as exc:
                            runtime['last_error'] = str(exc)
                            await send(ErrorEvent(message=f'所选语言准备失败，尚未开启收音：{exc}').model_dump(mode='json'))
                            continue
                    await send({'type': 'configured', 'source_language': config.source_language, 'asr_language': effective_language, 'target_language': config.target_language, 'language_pair': pipeline.language_pair})
                    language_label = {'zh': '锁定中文', 'ja': '锁定日语', 'en': '锁定英语', 'auto': '自动识别'}.get(effective_language, effective_language)
                    await send({'type': 'status', 'stage': 'models', 'message': f'语音识别已配置：{language_label}；翻译模型状态：{runtime["translation_status"]}'})
                    continue
                if kind == 'source_language':
                    try:
                        session.change_source_language(payload.get('source_language', 'auto'))
                    except ValueError as exc:
                        await send(ErrorEvent(message=str(exc)).model_dump(mode='json'))
                        continue
                    if not started:
                        session.start()
                        started = True
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
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            return
        finally:
            async def drain_session():
                try:
                    await session.close(drain=True)
                finally:
                    connections.pop(websocket, None)
                    done.set()
            # A disconnected client may cancel its endpoint while native work
            # is still running. Keep cleanup alive until that work truly ends.
            cleanup = asyncio.create_task(drain_session())
            cleanup_tasks.add(cleanup)
            cleanup.add_done_callback(cleanup_tasks.discard)
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                pass

    return app


app = create_app()
