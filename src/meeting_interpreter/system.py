from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


RECOMMENDED_OLLAMA_MODEL = "translategemma:4b"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/mac"
RECOMMENDED_ASR_MODEL = "mlx-community/whisper-medium-mlx-8bit"
_VERSION_RE = re.compile(r"(?:ollama version is |ollama version )?(v?\d+\.\d+\.\d+)", re.I)


def user_config_path() -> Path:
    return Path.home() / "Library/Application Support/LocalMeetingInterpreter/.env"


def preferences_path() -> Path:
    return user_config_path().with_name("preferences.json")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_preferences() -> dict[str, bool]:
    try:
        saved = json.loads(preferences_path().read_text(encoding="utf-8"))
        show_tips = saved.get("show_tips", True) if isinstance(saved, dict) else True
    except (OSError, ValueError):
        show_tips = True
    return {"show_tips": show_tips if type(show_tips) is bool else True}


def save_preferences(show_tips: bool) -> dict[str, bool]:
    if type(show_tips) is not bool:
        raise ValueError("提示设置必须为是或否。")
    preferences = {"show_tips": show_tips}
    _atomic_write(preferences_path(), json.dumps(preferences) + "\n")
    return preferences


def _ollama_path() -> str | None:
    candidates = [
        shutil.which("ollama"),
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        "/Applications/Ollama.app/Contents/Resources/ollama",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = _VERSION_RE.search(value)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).lstrip("v").split("."))


def _latest_ollama_version(timeout: float = 1.8) -> str | None:
    request = urllib.request.Request(
        "https://api.github.com/repos/ollama/ollama/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "LocalMeetingInterpreter"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload.get("tag_name") or "").lstrip("v") or None
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return None


def _ollama_models(timeout: float = 1.2) -> tuple[bool, list[str]]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = [str(item.get("name") or "") for item in payload.get("models", [])]
        return True, [name for name in names if name]
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False, []


def inspect_ollama(timeout: float = 1.8) -> dict[str, object]:
    path = _ollama_path()
    installed = path is not None
    version_output = ""
    current_version = None
    if path:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=timeout, check=False)
            version_output = (result.stdout or result.stderr or "").strip()
            current_version = (_VERSION_RE.search(version_output).group(1).lstrip("v") if _VERSION_RE.search(version_output) else None)
        except (OSError, subprocess.SubprocessError):
            pass
    reachable, models = _ollama_models(timeout=min(timeout, 1.2))
    latest_version = _latest_ollama_version(timeout=timeout) if installed else None
    current_tuple = _version_tuple(current_version)
    latest_tuple = _version_tuple(latest_version)
    return {
        "installed": installed,
        "path": path,
        "version": current_version,
        "version_output": version_output,
        "latest_version": latest_version,
        "update_available": bool(current_tuple and latest_tuple and current_tuple < latest_tuple),
        "version_check": "已是最新" if current_tuple and latest_tuple and current_tuple >= latest_tuple else ("有新版本" if current_tuple and latest_tuple else "无法联网核对"),
        "reachable": reachable,
        "models": models,
        "recommended_model": RECOMMENDED_OLLAMA_MODEL,
        "recommended_model_present": RECOMMENDED_OLLAMA_MODEL in models,
        "brew_available": bool(shutil.which("brew")),
    }


def upgrade_ollama(timeout: float = 120.0) -> dict[str, object]:
    brew = shutil.which("brew")
    if not brew:
        return {"ok": False, "message": "未找到 Homebrew，请从 ollama.com 手动更新 Ollama。"}
    try:
        result = subprocess.run([brew, "upgrade", "ollama"], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": f"升级命令启动失败：{exc}"}
    output = (result.stdout or result.stderr or "").strip()
    return {"ok": result.returncode == 0, "message": output[-1200:] or ("Ollama 已升级" if result.returncode == 0 else "Ollama 升级失败")}


def install_ollama(timeout: float = 600.0) -> dict[str, object]:
    """Install Ollama only after an explicit UI click.

    Homebrew is the unattended path. Without Homebrew we open the official
    installer page so macOS can apply its normal administrator approval flow.
    """
    if _ollama_path():
        return {"ok": True, "installed": True, "message": "Ollama 已安装，无需重复安装。"}
    brew = shutil.which("brew")
    if brew:
        try:
            result = subprocess.run([brew, "install", "ollama"], capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "message": f"安装命令启动失败：{exc}"}
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and _ollama_path():
            return {"ok": True, "installed": True, "message": output[-1200:] or "Ollama 已安装，请重新检查服务状态。"}
        return {"ok": False, "message": output[-1200:] or "Ollama 安装失败。"}
    try:
        subprocess.Popen(["open", OLLAMA_DOWNLOAD_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return {"ok": False, "message": f"无法打开 Ollama 官方安装页面：{exc}"}
    return {"ok": False, "requires_user": True, "message": "未检测到 Homebrew，已打开 Ollama 官方安装页面。完成安装后返回此处重新检查。"}


def pull_ollama_model(model: str = RECOMMENDED_OLLAMA_MODEL, timeout: float = 1800.0) -> dict[str, object]:
    path = _ollama_path()
    if not path:
        return {"ok": False, "message": "尚未安装 Ollama。"}
    if not model or any(char.isspace() for char in model):
        return {"ok": False, "message": "模型名称无效。"}
    try:
        result = subprocess.run([path, "pull", model], capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "message": f"模型下载启动失败：{exc}"}
    output = (result.stdout or result.stderr or "").strip()
    return {"ok": result.returncode == 0, "model": model, "message": output[-1600:] or ("推荐模型已准备好" if result.returncode == 0 else "推荐模型下载失败")}


def save_model_directory(model_dir: str, asr_engine: object = None) -> dict[str, object]:
    if asr_engine is not None and asr_engine not in ('whisper', 'sensevoice'):
        raise ValueError('请选择有效的语音识别引擎。')
    if any(char in model_dir for char in "\r\n\x00"):
        raise ValueError("模型目录不能包含换行或空字符。")
    path = Path(model_dir).expanduser()
    if not path.is_absolute():
        raise ValueError("模型目录必须是绝对路径。")
    path.mkdir(parents=True, exist_ok=True)
    config = user_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if config.is_file():
        existing = config.read_text(encoding="utf-8").splitlines()
    values = {
        "MEETING_INTERPRETER_MODEL_DIR": str(path),
        "HF_HOME": str(path / "huggingface"),
        "HUGGINGFACE_HUB_CACHE": str(path / "huggingface" / "hub"),
        "TRANSFORMERS_CACHE": str(path / "huggingface" / "transformers"),
    }
    if asr_engine is not None:
        values['MEETING_INTERPRETER_ASR_BACKEND'] = str(asr_engine)
    seen: set[str] = set()
    output: list[str] = []
    for line in existing:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in values:
            output.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    _atomic_write(config, "\n".join(output).rstrip() + "\n")
    return {"model_dir": str(path), "config_path": str(config), "restart_required": True}


def current_model_directory() -> str:
    try:
        for line in user_config_path().read_text(encoding="utf-8").splitlines():
            if line.startswith("MEETING_INTERPRETER_MODEL_DIR="):
                return str(Path(line.split("=", 1)[1].strip().strip("\"'")).expanduser())
    except OSError:
        pass
    configured = os.getenv("MEETING_INTERPRETER_MODEL_DIR")
    if configured:
        return str(Path(configured).expanduser())
    return str(Path.home() / "Library/Application Support/LocalMeetingInterpreter/models")


def inspect_asr_models(engine: str = "whisper") -> dict[str, object]:
    root = Path(current_model_directory()).expanduser()
    if engine == "sensevoice":
        folder = root / "asr" / "sensevoice"
        required = ["model.int8.onnx", "tokens.txt", "silero_vad.onnx"]
        present = [name for name in required if (folder / name).is_file()]
        return {"engine": engine, "model": "SenseVoice-Small", "installed": len(present) == len(required), "progress": round(len(present) / len(required) * 100), "path": str(folder), "missing": [name for name in required if name not in present], "message": "已连接，可使用" if len(present) == len(required) else "需要 model.int8.onnx、tokens.txt、silero_vad.onnx"}
    cache = root / "huggingface"
    marker = cache / "hub" / ("models--" + RECOMMENDED_ASR_MODEL.replace("/", "--"))
    installed = marker.is_dir() and any(marker.rglob("*.safetensors"))
    return {"engine": "whisper", "model": RECOMMENDED_ASR_MODEL, "installed": installed, "progress": 100 if installed else 0, "path": str(cache), "missing": [] if installed else ["Whisper 权重"], "message": "已连接，可使用" if installed else "尚未下载 Whisper 权重"}


def download_asr_model(engine: str = "whisper", timeout: float = 3600.0) -> dict[str, object]:
    if engine != "whisper":
        return {"ok": False, "message": "SenseVoice 权重需要导入本地 ONNX 文件；为避免下载错误版本，当前请在设置中指定模型目录。"}
    root = Path(current_model_directory()).expanduser()
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return {"ok": False, "message": "当前安装包缺少 huggingface_hub，请重新安装本地语音组件。"}
    try:
        snapshot_download(RECOMMENDED_ASR_MODEL, cache_dir=str(root / "huggingface"), local_files_only=False)
    except Exception as exc:
        return {"ok": False, "message": f"Whisper 模型下载失败：{exc}"}
    return {"ok": True, "engine": engine, "model": RECOMMENDED_ASR_MODEL, "message": "Whisper 语音模型已下载到本地模型目录。"}
