from __future__ import annotations

import asyncio
from typing import Protocol


LANGUAGE_CODES = {
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",
    "zh-tw": "zho_Hant",
    "ja": "jpn_Jpan",
    "japanese": "jpn_Jpan",
    "en": "eng_Latn",
    "english": "eng_Latn",
}


def nllb_language_code(language: str | None) -> str | None:
    if not language:
        return None
    normalized = language.strip().lower().replace("_", "-")
    return LANGUAGE_CODES.get(normalized)


class TranslationBackend(Protocol):
    async def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Translate one stable ASR segment without blocking the event loop."""


class MockTranslationBackend:
    async def translate(self, text: str, source_language: str, target_language: str) -> str:
        await asyncio.sleep(0.005)
        return text


class NLLBTranslationBackend:
    """Lazy transformers/NLLB adapter for local text translation."""

    def __init__(self, model_name: str, device: str = "auto") -> None:
        self.model_name = model_name
        self.device_name = device
        self._tokenizer = None
        self._model = None
        self._torch = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("translation requires: pip install -e '.[translation]'") from exc

        device = self.device_name
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name, torch_dtype=dtype)
        self._model.to(device)
        self.device_name = device

    async def translate(self, text: str, source_language: str, target_language: str) -> str:
        source_code = nllb_language_code(source_language)
        target_code = nllb_language_code(target_language)
        if not text or not target_code or not source_code or source_code == target_code:
            return text
        return await asyncio.to_thread(self._translate_sync, text, source_code, target_code)

    def _translate_sync(self, text: str, source_code: str, target_code: str) -> str:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        self._tokenizer.src_lang = source_code
        encoded = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        encoded = {key: value.to(self.device_name) for key, value in encoded.items()}
        forced_bos_token_id = self._tokenizer.convert_tokens_to_ids(target_code)
        with self._torch.inference_mode():
            generated = self._model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_new_tokens=256,
                num_beams=1,
            )
        return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
