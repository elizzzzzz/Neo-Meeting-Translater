from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


LanguagePair = Literal["zh-ja", "zh-en", "en-ja"]


class EventType(StrEnum):
    AUDIO = "audio"
    CAPTION = "caption"
    ERROR = "error"
    PING = "ping"


class AudioEvent(BaseModel):
    type: Literal["audio"] = "audio"
    session_id: str = Field(min_length=1, max_length=128)
    audio_base64: str = Field(min_length=1)
    sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    channels: int = Field(default=1, ge=1, le=2)
    source: Literal["microphone", "meeting_loopback", "file"] = "microphone"
    captured_at_ms: float | None = Field(default=None, ge=0)


class CaptionEvent(BaseModel):
    type: Literal["caption"] = "caption"
    session_id: str
    segment_id: str
    speaker_id: str
    source_language: str
    target_language: str
    language_pair: LanguagePair | None = None
    original_text: str
    translated_text: str
    is_final: bool = False
    skipped_stage: Literal['recognition', 'translation'] | None = None
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class SessionConfig(BaseModel):
    source_language: Literal["auto", "zh", "ja", "en"] = "auto"
    target_language: Literal["zh", "ja", "en"] = "zh"
    language_pair: LanguagePair | None = None
    mode: Literal["mock", "local"] = "mock"
    speaker_mode: Literal["none", "embedding", "pyannote"] = "none"
