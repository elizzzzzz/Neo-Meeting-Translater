"""Replay a local Chinese WAV and synthetic non-speech through cached models.

No microphone, model download, settings change, or external inference is used.
Run with an Apple Silicon Python and PYTHONPATH=src. Use --ollama to also
exercise the installed local translation model through the WebSocket endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import time
import wave

os.environ["HF_HUB_OFFLINE"] = "1"

import numpy as np
from huggingface_hub import snapshot_download

from meeting_interpreter.asr import MLXWhisperBackend
from meeting_interpreter.models import AudioEvent
from meeting_interpreter.pipeline import Pipeline


async def verify(args) -> dict:
    model = args.model if Path(args.model).is_dir() else snapshot_download(args.model, local_files_only=True)
    with wave.open(str(args.audio)) as recording:
        assert (recording.getframerate(), recording.getnchannels(), recording.getsampwidth()) == (16000, 1, 2), "Requires mono 16 kHz PCM16 WAV"
        speech = np.frombuffer(recording.readframes(recording.getnframes()), dtype=np.int16)
    backend = MLXWhisperBackend(model, "zh")
    rng = np.random.default_rng(20261104)
    cases = {
        "silence": np.zeros(64000, dtype=np.int16),
        "quiet_noise": rng.normal(0, 130, 64000).astype(np.int16),
        "noise": rng.normal(0, 350, 64000).astype(np.int16),
        "hum": (500 * np.sin(np.arange(64000) * 2 * np.pi * 100 / 16000)).astype(np.int16),
        "chinese_speech": speech,
    }
    results = {}
    for name, data in cases.items():
        started = time.monotonic()
        result = await backend.transcribe(data.tobytes(), 16000, 0)
        results[name] = {"elapsed_s": round(time.monotonic() - started, 3), "result": result.text if result else None}
        print(name, results[name], flush=True)
        if name == "chinese_speech":
            assert result and any("\u3400" <= char <= "\u9fff" for char in result.text)
        else:
            assert result is None, f"Non-speech produced text: {name}"
    pipeline = Pipeline(mode="local", source_language="zh", target_language="zh", asr_backend=backend)
    updates = []
    for position in range(0, len(speech), 1600):
        event = AudioEvent(session_id="real-chinese", audio_base64=base64.b64encode(speech[position:position + 1600].tobytes()).decode())
        updates.extend([caption.model_dump() async for caption in pipeline.process_audio(event)])
    assert updates and all(caption["source_language"] == "zh" for caption in updates)
    results["streaming_chinese"] = updates
    print("streaming_chinese", [(c["segment_id"], c["original_text"]) for c in updates], flush=True)
    if args.ollama:
        results["websocket"] = await asyncio.to_thread(verify_websocket, model, speech)
    return results


def verify_websocket(model: str, speech) -> dict:
    from fastapi.testclient import TestClient
    os.environ.update(MEETING_INTERPRETER_MODE="local", MEETING_INTERPRETER_ASR_MODEL=model,
                      MEETING_INTERPRETER_TRANSLATION_BACKEND="ollama")
    from meeting_interpreter.app import create_app
    with TestClient(create_app()) as client:
        deadline = time.monotonic() + 300
        while True:
            health = client.get("/health").json()
            if health["models"]["ready"]:
                break
            assert health["models"]["stage"] != "error", health
            assert time.monotonic() < deadline, "Warmup timed out"
            time.sleep(.2)
        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "config", "source_language": "zh", "target_language": "ja"})
            configured = socket.receive_json()
            assert configured["asr_language"] == "zh", configured
            socket.receive_json()
            socket.send_json(AudioEvent(session_id="ws-replay", audio_base64=base64.b64encode(speech[:64000].tobytes()).decode()).model_dump())
            captions = []
            while True:
                message = socket.receive_json()
                assert message["type"] != "error", message
                if message["type"] == "caption":
                    captions.append(message)
                    if message["is_final"] and message["translated_text"]:
                        break
            assert captions[0]["original_text"]
            assert captions[-1]["source_language"] == "zh"
            assert any("\u3040" <= char <= "\u30ff" for char in captions[-1]["translated_text"])
            print("websocket", captions, flush=True)
            # Drain a deterministic response to a silent frame before checking
            # that no subtitle was generated: pong comes after audio processing.
            socket.send_json(AudioEvent(session_id="silent-replay", audio_base64=base64.b64encode(bytes(32000)).decode()).model_dump())
            socket.send_json({"type": "ping"})
            while True:
                message = socket.receive_json()
                assert message["type"] not in {"caption", "error"}, message
                if message["type"] == "pong":
                    break
            return {"configured": configured, "captions": captions, "silence_has_no_caption": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--model", default="mlx-community/whisper-medium-mlx-8bit")
    parser.add_argument("--ollama", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("artifacts/debug/chinese-recognition-0.2.2.json"))
    args = parser.parse_args()
    report = asyncio.run(verify(args))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Passed; report:", args.report, flush=True)
