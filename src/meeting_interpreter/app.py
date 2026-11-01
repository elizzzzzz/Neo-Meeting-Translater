from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .models import AudioEvent, ErrorEvent
from .pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"


def create_app() -> FastAPI:
    mode = os.getenv("MEETING_INTERPRETER_MODE", "mock")
    app = FastAPI(title="Local Meeting Interpreter", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": mode}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

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
                try:
                    event = AudioEvent.model_validate(payload)
                    async for caption in pipeline.process_audio(event):
                        await websocket.send_json(caption.model_dump(mode="json"))
                except Exception as exc:  # Surface errors to the UI without dropping the session.
                    await websocket.send_json(ErrorEvent(message=str(exc)).model_dump(mode="json"))
        except WebSocketDisconnect:
            return

    return app


app = create_app()
