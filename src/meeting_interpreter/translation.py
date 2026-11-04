from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
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

LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "ja": "Japanese",
    "japanese": "Japanese",
    "en": "English",
    "english": "English",
}


def _safe_correction(original: str, candidate: str, language: str) -> bool:
    """Reject hallucinated correction output before it reaches the transcript."""
    if len(candidate) > max(96, len(original) * 2 + 24):
        return False
    original_digits = re.findall(r"\d+(?:[.,]\d+)?", original)
    if any(digit not in candidate for digit in original_digits):
        return False
    if language.lower().startswith("japanese") or language.lower() in {"ja", "jpn"}:
        allowed = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]", candidate))
        return allowed >= max(1, len(re.findall(r"[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]", original)) // 3)
    if language.lower().startswith("simplified chinese") or language.lower() in {"zh", "zho"}:
        allowed = len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", candidate))
        return allowed >= max(1, len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", original)) // 3)
    return True


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


class OllamaTranslationBackend:
    """Local Ollama adapter for low-latency text translation.

    The HTTP request is kept dependency-free so the packaged macOS app can use
    an Ollama installation without bundling another client library.
    """

    def __init__(
        self,
        model: str = "translategemma:4b",
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 180.0,
        keep_alive: str = "24h",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive

    async def translate(self, text: str, source_language: str, target_language: str) -> str:
        if not text or not target_language:
            return text
        source_key = source_language.strip().lower().replace("_", "-") if source_language else ""
        target_key = target_language.strip().lower().replace("_", "-")
        source_name = LANGUAGE_NAMES.get(source_key)
        target_name = LANGUAGE_NAMES.get(target_key)
        if not target_name or not source_name or source_key == target_key:
            return text
        return await asyncio.to_thread(self._translate_sync, text, source_name, target_name)

    async def correct_source(self, text: str, context: str, language: str) -> str:
        """Apply a conservative local context pass to a stable ASR chunk.

        The correction prompt is deliberately separate from translation: the
        model may fix homophones, punctuation and obvious segmentation errors,
        but it is forbidden from adding facts that were not spoken.
        """
        source_name = LANGUAGE_NAMES.get((language or "").strip().lower(), language)
        if not text or not source_name:
            return text
        return await asyncio.to_thread(self._correct_source_sync, text, context, source_name)

    def _request(self, text: str, source_name: str, target_name: str, stream: bool):
        prompt = (
            f"Translate the following meeting utterance from {source_name} to {target_name}. "
            "Output only the translation. Preserve names, numbers, and punctuation.\n\n"
            f"{text}"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": 2048,
                "num_predict": 256,
            },
        }
        return urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def _correct_source_sync(self, text: str, context: str, source_name: str) -> str:
        prompt = (
            f"You are correcting a {source_name} meeting transcript. Return only the corrected transcript. "
            "Fix likely homophones, missing punctuation, and obvious word boundary errors using the context. "
            "Keep the meaning, names, numbers, and language. Never add information, explanations, or a translation.\n\n"
            f"Context from the same meeting:\n{context[-600:]}\n\nCandidate transcript:\n{text}"
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 256},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return text
        candidate = re.sub(r"<think>.*?</think>", "", str(body.get("response", "")), flags=re.DOTALL).strip()
        if candidate.startswith("```") and candidate.endswith("```"):
            candidate = candidate[3:-3].strip()
        if not candidate or not _safe_correction(text, candidate, language=source_name):
            return text
        return candidate
    def _translate_sync(self, text: str, source_name: str, target_name: str) -> str:
        request = self._request(text, source_name, target_name, False)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            try:
                detail = str(json.loads(detail).get("error") or detail)
            except (ValueError, AttributeError):
                pass
            raise RuntimeError(f"Ollama 模型 {self.model} 运行失败（HTTP {exc.code}）：{detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"无法连接 Ollama（{self.base_url}）。请确认 Ollama 正在运行。"
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Ollama 模型 {self.model} 加载或翻译超时（{self.timeout:.0f}s）。"
            ) from exc

        if body.get("error"):
            raise RuntimeError(f"Ollama 翻译失败：{body['error']}")
        result = str(body.get("response", "")).strip()
        result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()
        if result.startswith("```") and result.endswith("```"):
            result = result[3:-3].strip()
        if not result:
            raise RuntimeError(f"Ollama 模型 {self.model} 返回了空翻译。")
        return result

    async def stream_translate(self, text: str, source_language: str, target_language: str):
        """Yield accumulating translation as local Ollama generates tokens."""
        source_name = LANGUAGE_NAMES.get(source_language)
        target_name = LANGUAGE_NAMES.get(target_language)
        if not text or not source_name or not target_name or source_language == target_language:
            yield text
            return
        response = None
        result = ''
        done = False
        request = self._request(text, source_name, target_name, True)
        try:
            response = await asyncio.to_thread(urllib.request.urlopen, request, timeout=self.timeout)
            while True:
                line = await asyncio.to_thread(response.readline, 1024 * 1024)
                if not line:
                    break
                body = json.loads(line)
                if body.get('error'):
                    raise RuntimeError(f"Ollama 翻译失败：{body['error']}")
                token = str(body.get('response', ''))
                if token:
                    result += token
                    yield result.strip()
                if body.get('done'):
                    done = True
                    break
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode('utf-8', errors='replace')
            raise RuntimeError(f'Ollama 翻译失败（HTTP {exc.code}）：{detail}') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f'无法连接 Ollama（{self.base_url}）：{exc}') from exc
        except TimeoutError as exc:
            raise RuntimeError(f'Ollama 翻译超时（{self.timeout:.0f}s）') from exc
        finally:
            if response is not None:
                # Close this recording's HTTP stream on completion/disconnect.
                await asyncio.to_thread(response.close)
        if not done:
            raise RuntimeError('Ollama 翻译流中断，译文尚未完成，请核对原文')
        if not result.strip():
            raise RuntimeError(f'Ollama 模型 {self.model} 返回了空翻译。')
