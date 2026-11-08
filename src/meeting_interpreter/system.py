from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .local_services import SERVICE_URLS, local_url, inspect_service, match_service_model


RECOMMENDED_OLLAMA_MODEL = "translategemma:4b"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/mac"
RECOMMENDED_ASR_MODEL = "mlx-community/whisper-medium-mlx-8bit"
_VERSION_RE = re.compile(r"(?:ollama version is |ollama version )?(v?\d+\.\d+\.\d+)", re.I)
_PREFERENCES_LOCK = threading.Lock()


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


def read_preferences() -> dict[str, object]:
    saved = {}
    try:
        saved = json.loads(preferences_path().read_text(encoding="utf-8"))
        show_tips = saved.get("show_tips", True) if isinstance(saved, dict) else True
    except (OSError, ValueError):
        show_tips = True
    result = {"show_tips": show_tips if type(show_tips) is bool else True}
    if isinstance(saved, dict) and saved.get('interface_language') in ('auto', 'zh', 'ja', 'en'):
        result['interface_language'] = saved['interface_language']
    if isinstance(saved, dict) and saved.get('appearance') in ('system', 'light', 'dark'):
        result['appearance'] = saved['appearance']
    return result


def startup_preferences() -> dict[str, object]:
    preferences = read_preferences()
    # Saving configuration, rather than model availability, completes setup.
    # This also recognizes releases that predate the onboarding preference.
    configured = saved_config()
    completed = any(configured.get(key) for key in (
        'MEETING_INTERPRETER_MODEL_DIR', 'MEETING_INTERPRETER_ASR_BACKEND',
        'MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL',
        'MEETING_INTERPRETER_TRANSLATION_BACKEND', 'MEETING_INTERPRETER_OLLAMA_MODEL',
        'MEETING_INTERPRETER_TRANSLATION_MODEL', 'MEETING_INTERPRETER_LLAMA_MODEL',
        'MEETING_INTERPRETER_SGLANG_MODEL',
    ))
    return {**preferences, 'setup_completed': completed,
            'show_tips': bool(preferences['show_tips']) and not completed}


def save_preferences(show_tips: bool | None = None, interface_language: str | None = None, appearance: str | None = None) -> dict[str, object]:
    if show_tips is None and interface_language is None and appearance is None:
        raise ValueError('请提供提示、界面语言或外观设置。')
    if show_tips is not None and type(show_tips) is not bool:
        raise ValueError("提示设置必须为是或否。")
    if interface_language is not None and interface_language not in ('auto', 'zh', 'ja', 'en'):
        raise ValueError('界面语言必须为自动、中文、日语或英语。')
    if appearance is not None and appearance not in ('system', 'light', 'dark'):
        raise ValueError('外观必须为跟随系统、亮色或暗色。')
    with _PREFERENCES_LOCK:
        preferences = read_preferences()
        if show_tips is not None:
            preferences['show_tips'] = show_tips
        if interface_language is not None:
            preferences['interface_language'] = interface_language
        if appearance is not None:
            preferences['appearance'] = appearance
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
    recommended = match_service_model(RECOMMENDED_OLLAMA_MODEL, [{'id': name} for name in models])
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
        "recommended_model": recommended,
        "recommended_model_present": recommended in models,
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


def save_model_directory(model_dir: str, asr_engine: object = None, selection: dict | None = None) -> dict[str, object]:
    if asr_engine is not None and asr_engine not in ('whisper', 'sensevoice', 'apple', 'ollama', 'llama'):
        raise ValueError('请选择有效的语音识别引擎。')
    extra = {}
    if selection:
        asr_engine = asr_engine or os.getenv('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
        translation = selection.get('translation_backend', os.getenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'ollama'))
        if translation not in (*SERVICE_URLS, 'nllb'):
            raise ValueError('请选择 Ollama、llama.app、SGLang 或内置翻译引擎。')
        for field in ('asr_model', 'translation_model'):
            if field in selection:
                value = selection[field]
                # An empty catalogue is an unconfigured model, not a reason to
                # discard changes to another model or service.
                if not isinstance(value, str) or any(c in value for c in '\r\n\x00"\''):
                    raise ValueError('请选择有效的模型名称。')
        if 'asr_model' in selection:
            key = 'MEETING_INTERPRETER_SERVICE_ASR_MODEL' if asr_engine in SERVICE_URLS else 'MEETING_INTERPRETER_ASR_MODEL'
            if asr_engine not in ('sensevoice', 'apple'):
                extra[key] = selection['asr_model'].strip()
        if asr_engine in SERVICE_URLS:
            extra['MEETING_INTERPRETER_ASR_URL'] = local_url(selection.get('asr_url') or SERVICE_URLS[asr_engine])
        extra['MEETING_INTERPRETER_TRANSLATION_BACKEND'] = translation
        if 'translation_model' in selection:
            key = f'MEETING_INTERPRETER_{translation.upper()}_MODEL' if translation in SERVICE_URLS else 'MEETING_INTERPRETER_TRANSLATION_MODEL'
            extra[key] = selection['translation_model'].strip()
        if translation in SERVICE_URLS:
            key = f'MEETING_INTERPRETER_{translation.upper()}_URL'
            extra[key] = local_url(selection.get('translation_url') or SERVICE_URLS[translation])
    if any(char in model_dir for char in "\r\n\x00"):
        raise ValueError("模型目录不能包含换行或空字符。")
    path = Path(model_dir).expanduser()
    if not path.is_absolute():
        raise ValueError("模型目录必须是绝对路径。")
    # Saving preferences must not depend on model storage being available.
    # Ollama/llama own their storage, and an external disk may be disconnected.
    # Only a subsequent explicit download should create model directories.
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
    previous = {**os.environ, **saved_config(), **extra}
    relocated = _relocated_values(previous, path)
    values.update(extra)
    engine = str(asr_engine or previous.get('MEETING_INTERPRETER_ASR_BACKEND', 'whisper'))
    removed = set()
    if engine == 'sensevoice':
        values['MEETING_INTERPRETER_SENSEVOICE_MODEL'] = str(sensevoice_location(path))
        removed.update(('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL'))
    elif engine == 'apple':
        removed.update(('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SENSEVOICE_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL'))
    elif engine == 'whisper':
        selected = previous.get('MEETING_INTERPRETER_ASR_MODEL', RECOMMENDED_ASR_MODEL)
        info = inspect_asr_models('whisper', selected, str(path))
        values['MEETING_INTERPRETER_ASR_MODEL'] = str(info['model'])
        removed.update(('MEETING_INTERPRETER_SENSEVOICE_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL'))
    else:
        removed.update(('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SENSEVOICE_MODEL'))
    if 'MEETING_INTERPRETER_TRANSLATION_MODEL' in relocated:
        values['MEETING_INTERPRETER_TRANSLATION_MODEL'] = relocated['MEETING_INTERPRETER_TRANSLATION_MODEL']
    if asr_engine is not None:
        values['MEETING_INTERPRETER_ASR_BACKEND'] = engine
    seen: set[str] = set()
    output: list[str] = []
    for line in existing:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in removed:
            continue
        if key in values:
            if key in seen:
                continue
            output.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    _atomic_write(config, "\n".join(output).rstrip() + "\n")
    persisted = saved_config()
    if any(persisted.get(key) != value for key, value in values.items()) or removed.intersection(persisted):
        raise OSError('配置写入后核对失败，请重新保存设置。')
    return {"model_dir": str(path), "config_path": str(config), "restart_required": False,
            "saved": True, "settings": model_settings()}


def saved_config() -> dict[str, str]:
    for config in (user_config_path(), Path.home() / '.config/local-meeting-interpreter/.env'):
        if not config.is_file():
            continue
        values = {}
        for line in config.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip("\"'")
        return values
    return {}


def ollama_model_directory() -> str:
    """Read Ollama's configured directory without changing its service."""
    configured = os.getenv('OLLAMA_MODELS', '')
    if not configured:
        try:
            result = subprocess.run(['/bin/launchctl', 'getenv', 'OLLAMA_MODELS'],
                                    capture_output=True, text=True, timeout=1, check=False)
            configured = result.stdout.strip() if result.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            pass
    path = Path(configured).expanduser() if configured else Path.home() / '.ollama/models'
    return str(path.resolve())


def current_model_directory() -> str:
    configured = saved_config().get('MEETING_INTERPRETER_MODEL_DIR') or os.getenv('MEETING_INTERPRETER_MODEL_DIR')
    return str(Path(configured).expanduser()) if configured else ollama_model_directory()


def _cache_roots(root: Path) -> list[Path]:
    return [root / 'huggingface/hub', root / 'hub', root, root / 'huggingface']


def _model_files(folder: Path, engine: str) -> bool:
    if not (folder / 'config.json').is_file():
        return False
    if engine == 'whisper':
        weights = [folder / name for name in ('weights.safetensors', 'weights.npz') if (folder / name).is_file()]
    else:
        weights = list(folder.glob('*.safetensors')) + list(folder.glob('pytorch_model*.bin'))
    if not weights or not all(p.is_file() and p.stat().st_size > 0 for p in weights):
        return False
    # A partial sharded download must not be reported ready.
    for index in folder.glob('*.index.json'):
        try:
            parts = set(json.loads(index.read_text()).get('weight_map', {}).values())
            if any(not (folder / part).is_file() for part in parts):
                return False
        except (OSError, ValueError):
            return False
    return True


def _repo_name(selected: str) -> str:
    for part in Path(selected).parts:
        if part.startswith('models--'):
            return part.removeprefix('models--').replace('--', '/')
    return selected


def resolve_model_location(selected: str, root: Path, engine: str = 'whisper') -> str | None:
    """Resolve files in the chosen directory, never a pinned snapshot in an old root."""
    chosen = Path(selected).expanduser()
    if chosen.is_absolute() and chosen.is_relative_to(root) and _model_files(chosen, engine):
        return str(chosen)
    if _model_files(root, engine):
        return str(root)
    repo = _repo_name(selected)
    for cache in _cache_roots(root):
        marker = cache / ('models--' + repo.replace('/', '--'))
        snapshots = marker / 'snapshots'
        ref = marker / 'refs/main'
        candidates = []
        if ref.is_file():
            candidates.append(snapshots / ref.read_text().strip())
        if snapshots.is_dir():
            candidates.extend(sorted(snapshots.iterdir(), key=lambda p: p.name))
        for folder in candidates:
            if _model_files(folder, engine):
                return str(folder)
    relative = repo if not Path(repo).is_absolute() else Path(repo).name
    for folder in (root / relative, root / Path(relative).name, root / 'asr' / Path(relative).name):
        if _model_files(folder, engine):
            return str(folder)
    return None



def sensevoice_location(root: Path, explicit: str | None = None) -> Path:
    candidates = [root, root / 'asr/sensevoice', root / 'sensevoice']
    if explicit:
        selected = Path(explicit).expanduser()
        if selected.is_relative_to(root):
            candidates.insert(0, selected)
    required = ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx')
    return next((folder for folder in candidates if all((folder / name).is_file() for name in required)), root / 'asr/sensevoice')


def _available_models(root: Path, engine: str) -> dict[str, str]:
    models = {}
    if _model_files(root, engine):
        models[str(root)] = str(root)
    # Only inspect bounded, known model locations, never scan service blobs.
    for base in (root, root / 'asr'):
        if base.is_dir():
            for folder in sorted(base.iterdir()):
                if folder.is_dir() and _model_files(folder, engine):
                    models[str(folder)] = str(folder)
    for cache in _cache_roots(root):
        if not cache.is_dir():
            continue
        for marker in sorted(cache.glob('models--*')):
            repo = marker.name.removeprefix('models--').replace('--', '/')
            if engine == 'whisper' and 'whisper' not in repo.lower():
                continue
            resolved = resolve_model_location(repo, root, engine)
            if resolved:
                models[repo] = resolved
    return models

def _relocated_values(values: dict[str, str], root: Path) -> dict[str, str]:
    result = dict(values)
    for key, engine in (('MEETING_INTERPRETER_ASR_MODEL', 'whisper'), ('MEETING_INTERPRETER_TRANSLATION_MODEL', 'nllb')):
        selected = result.get(key)
        if selected and Path(selected).expanduser().is_absolute():
            resolved = resolve_model_location(selected, root, engine)
            # Keep the expected new location visible when files are absent.
            repo = _repo_name(selected)
            missing = root / 'huggingface/hub' / ('models--' + repo.replace('/', '--')) / 'snapshots' / Path(selected).name if repo != selected else root / Path(selected).name
            result[key] = resolved or str(missing)
    previous = values.get('MEETING_INTERPRETER_MODEL_DIR')
    sensevoice = values.get('MEETING_INTERPRETER_SENSEVOICE_MODEL')
    if previous and sensevoice and Path(sensevoice).expanduser().is_relative_to(Path(previous).expanduser()):
        result['MEETING_INTERPRETER_SENSEVOICE_MODEL'] = str(root / Path(sensevoice).expanduser().relative_to(Path(previous).expanduser()))
    return result


def load_user_config() -> None:
    """Apply saved model choices before importing libraries that cache HF locations."""
    values = saved_config()
    root = Path(values.get('MEETING_INTERPRETER_MODEL_DIR') or os.getenv('MEETING_INTERPRETER_MODEL_DIR') or ollama_model_directory()).expanduser()
    values = _relocated_values(values, root)
    if 'MEETING_INTERPRETER_ASR_BACKEND' in values:
        engine = values['MEETING_INTERPRETER_ASR_BACKEND']
        keys = {'whisper': ('MEETING_INTERPRETER_SENSEVOICE_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL'),
                'sensevoice': ('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL'),
                'apple': ('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SENSEVOICE_MODEL', 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL')}.get(engine, ('MEETING_INTERPRETER_ASR_MODEL', 'MEETING_INTERPRETER_SENSEVOICE_MODEL'))
        for key in keys:
            values.pop(key, None)
            os.environ.pop(key, None)
    for key, value in values.items():
        if key.startswith(('MEETING_INTERPRETER_ASR_', 'MEETING_INTERPRETER_SERVICE_ASR_', 'MEETING_INTERPRETER_TRANSLATION_', 'MEETING_INTERPRETER_OLLAMA_', 'MEETING_INTERPRETER_LLAMA_', 'MEETING_INTERPRETER_SGLANG_', 'MEETING_INTERPRETER_SENSEVOICE_')):
            os.environ[key] = value
        elif key not in os.environ:
            os.environ[key] = value
    os.environ.update(MEETING_INTERPRETER_MODEL_DIR=str(root), HF_HOME=str(root / 'huggingface'),
                      HUGGINGFACE_HUB_CACHE=str(root / 'huggingface/hub'), TRANSFORMERS_CACHE=str(root / 'huggingface/transformers'))
    for key, engine in (('MEETING_INTERPRETER_ASR_MODEL', 'whisper'), ('MEETING_INTERPRETER_TRANSLATION_MODEL', 'nllb')):
        if key == 'MEETING_INTERPRETER_ASR_MODEL' and os.getenv('MEETING_INTERPRETER_ASR_BACKEND') == 'apple':
            continue
        selected = os.getenv(key, RECOMMENDED_ASR_MODEL if engine == 'whisper' else 'facebook/nllb-200-distilled-600M')
        resolved = resolve_model_location(selected, root, engine)
        if resolved:
            os.environ[key] = resolved

    if os.getenv('MEETING_INTERPRETER_ASR_BACKEND') == 'sensevoice':
        os.environ['MEETING_INTERPRETER_SENSEVOICE_MODEL'] = str(sensevoice_location(root, values.get('MEETING_INTERPRETER_SENSEVOICE_MODEL')))
    engine = os.getenv('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
    provider = os.getenv('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'nllb')
    roles = []
    if engine in SERVICE_URLS:
        roles.append((engine, 'MEETING_INTERPRETER_SERVICE_ASR_MODEL', 'MEETING_INTERPRETER_ASR_URL', 'asr'))
    if provider in SERVICE_URLS:
        roles.append((provider, f'MEETING_INTERPRETER_{provider.upper()}_MODEL',
                      f'MEETING_INTERPRETER_{provider.upper()}_URL', 'translation'))
    for provider, model_key, url_key, role in roles:
        selected = os.getenv(model_key, 'translategemma:4b' if provider == 'ollama' and role == 'translation' else '')
        if selected and '/' not in selected:
            try:
                info = inspect_service(provider, os.getenv(url_key) or SERVICE_URLS[provider])
                os.environ[model_key] = match_service_model(selected, [m for m in info['models'] if m.get(role, True)])
            except ValueError:
                pass


def model_settings() -> dict:
    """Read pending saved selections without changing active warmed models."""
    values = {**os.environ, **saved_config()}
    engine = values.get('MEETING_INTERPRETER_ASR_BACKEND', 'whisper')
    provider = values.get('MEETING_INTERPRETER_TRANSLATION_BACKEND', 'nllb')
    root = current_model_directory()
    return {'model_dir': root, 'model_dir_exists': Path(root).is_dir(), 'ollama_model_dir': ollama_model_directory(), 'asr_engine': engine,
            'asr_model': 'Apple SpeechAnalyzer' if engine == 'apple' else 'SenseVoice-Small' if engine == 'sensevoice' else values.get('MEETING_INTERPRETER_SERVICE_ASR_MODEL', '') if engine in SERVICE_URLS else values.get('MEETING_INTERPRETER_ASR_MODEL', RECOMMENDED_ASR_MODEL),
            'asr_url': values.get('MEETING_INTERPRETER_ASR_URL', SERVICE_URLS.get(engine, '')),
            'translation_backend': provider,
            'translation_model': values.get(f'MEETING_INTERPRETER_{provider.upper()}_MODEL' if provider in SERVICE_URLS else 'MEETING_INTERPRETER_TRANSLATION_MODEL', 'translategemma:4b' if provider == 'ollama' else 'facebook/nllb-200-distilled-600M' if provider == 'nllb' else ''),
            'translation_url': values.get(f'MEETING_INTERPRETER_{provider.upper()}_URL', SERVICE_URLS.get(provider, ''))}


def inspect_asr_models(engine: str = 'whisper', model: str | None = None, model_dir: str | None = None, languages=None) -> dict[str, object]:
    if engine == 'apple':
        from .apple_speech import inspect_apple_speech
        return inspect_apple_speech(languages)
    root = Path(model_dir or current_model_directory()).expanduser()
    if not root.is_absolute():
        raise ValueError('模型目录必须是绝对路径。')
    values = {**os.environ, **saved_config()}
    if engine == 'sensevoice':
        explicit = values.get('MEETING_INTERPRETER_SENSEVOICE_MODEL')
        folder = sensevoice_location(root, explicit)
        # Legacy standalone configuration without a model root remains supported.
        if explicit and model_dir is None and not values.get('MEETING_INTERPRETER_MODEL_DIR'):
            folder = Path(explicit).expanduser()
        required = ['model.int8.onnx', 'tokens.txt', 'silero_vad.onnx']
        present = [name for name in required if (folder / name).is_file()]
        installed = len(present) == len(required)
        return {'engine': engine, 'model': 'SenseVoice-Small', 'models': ['SenseVoice-Small'], 'installed': installed, 'progress': round(len(present) / len(required) * 100), 'path': str(folder), 'missing': [name for name in required if name not in present], 'message': '已连接，可使用' if installed else '需要 model.int8.onnx、tokens.txt、silero_vad.onnx'}
    selected = model or values.get('MEETING_INTERPRETER_TRANSLATION_MODEL' if engine == 'nllb' else 'MEETING_INTERPRETER_ASR_MODEL', 'facebook/nllb-200-distilled-600M' if engine == 'nllb' else RECOMMENDED_ASR_MODEL)
    resolved = resolve_model_location(selected, root, engine)
    installed = resolved is not None
    # Preserve repository IDs but replace stale absolute paths with their new location.
    if resolved and (Path(selected).is_absolute() or resolved == str(root)):
        selected = resolved
    available = _available_models(root, engine)
    if not installed:
        # The chosen directory owns the selection; never retain a historical path.
        if len(available) == 1:
            selected, resolved = next(iter(available.items()))
            installed = True
        else:
            selected = ''
    models = list(dict.fromkeys(([selected] if selected else []) + list(available)))
    message = '本地文件已找到' if installed else ('目录不存在或外置盘未挂载，请重新选择目录' if not root.is_dir() else '所选模型未在此目录找到，请选择已检测到的模型')
    return {'engine': engine, 'model': selected, 'models': list(dict.fromkeys(models)), 'installed': installed,
            'resolved_model': resolved, 'progress': 100 if installed else 0, 'path': str(root),
            'missing': [] if installed else ['模型权重'], 'message': message}


def download_asr_model(engine: str = "whisper", timeout: float = 3600.0, model: str | None = None, languages=None) -> dict[str, object]:
    if engine == "apple":
        from .apple_speech import install_apple_speech
        return install_apple_speech(languages, timeout)
    if engine != "whisper":
        return {"ok": False, "message": "SenseVoice 权重需要导入本地 ONNX 文件；为避免下载错误版本，当前请在设置中指定模型目录。"}
    root = Path(current_model_directory()).expanduser()
    selected = model or RECOMMENDED_ASR_MODEL
    if 'whisper' not in selected.lower() or any(c in selected for c in '\r\n\x00'):
        return {'ok': False, 'message': '请选择 Whisper 模型；其他模型请通过 Ollama 或 llama.app 管理。'}
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return {"ok": False, "message": "当前安装包缺少 huggingface_hub，请重新安装本地语音组件。"}
    try:
        snapshot_download(selected, cache_dir=str(root / "huggingface" / 'hub'), local_files_only=False)
    except Exception as exc:
        return {"ok": False, "message": f"Whisper 模型下载失败：{exc}"}
    return {"ok": True, "engine": engine, "model": selected, "message": "Whisper 语音模型已下载到本地模型目录。"}
