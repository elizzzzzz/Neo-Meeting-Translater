from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import AudioEvent, ErrorEvent, SessionConfig
from .pipeline import Pipeline

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    app = FastAPI(title="Local Meeting Interpreter", version="0.1.0")
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": mode}

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
                    continue
                try:
                    event = AudioEvent.model_validate(payload)
                    async for caption in pipeline.process_audio(event):
                        try:
                            await websocket.send_json(caption.model_dump(mode="json"))
                        except WebSocketDisconnect:
                            return
                except Exception as exc:  # Surface errors to the UI without dropping the session.
                    try:
                        await websocket.send_json(ErrorEvent(message=str(exc)).model_dump(mode="json"))
                    except WebSocketDisconnect:
                        return
        except WebSocketDisconnect:
            return

    return app


app = create_app()
