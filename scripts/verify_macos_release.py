"""Verify the actual delivered archives, including ZIP permissions and symlinks."""
from __future__ import annotations

import plistlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def run(*args: str) -> bytes:
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=120)
    except subprocess.CalledProcessError as exc:
        detail = exc.output.decode('utf-8', errors='replace')
        raise RuntimeError(f"command failed ({exc.returncode}): {' '.join(args)}\n{detail}") from exc


def verify_bundle(app: Path) -> None:
    executable = app / 'Contents/MacOS/LocalMeetingInterpreter'
    assert executable.is_file(), f'Missing app executable: {app}'
    assert executable.stat().st_mode & 0o111, f'Executable permissions missing: {executable}'
    assert b'arm64' in run('lipo', '-archs', str(executable)), 'Wrong app architecture'
    assert (app / 'Contents/Resources/web/index.html').is_file(), 'Missing embedded UI'
    assert (app / 'Contents/Frameworks/mlx.metallib').is_file(), 'Missing MLX GPU library beside libmlx.dylib; native ASR startup would crash'
    assert (app / 'Contents/Frameworks/sherpa_onnx/lib/libonnxruntime.dylib').is_file(), 'Missing local speech/voice runtime library'
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    assert info.get('NSMicrophoneUsageDescription'), 'Missing microphone usage description'
    assert info.get('CFBundleIdentifier') == 'com.localmeetinginterpreter.app', 'Wrong bundle identifier'
    run('codesign', '--verify', '--deep', '--strict', str(app))
    print(f'Verified signed arm64 bundle: {app}', flush=True)


def main(directory: Path) -> None:
    archive = directory / 'LocalMeetingInterpreter-portable.zip'
    assert archive.is_file() and archive.stat().st_size > 0, f'Missing portable archive: {archive}'
    with zipfile.ZipFile(archive) as zipped:
        assert not any(Path(name).name.startswith('._') or name.startswith('__MACOSX/') for name in zipped.namelist()), 'ZIP contains resource-fork metadata'
    with tempfile.TemporaryDirectory(prefix='lmi-zip-verify-', dir='/private/tmp') as folder:
        run('ditto', '-x', '-k', str(archive), folder)
        verify_bundle(Path(folder) / 'LocalMeetingInterpreter.app')
    image = directory / 'LocalMeetingInterpreter.dmg'
    assert image.is_file() and image.stat().st_size > 0, f'Missing DMG archive: {image}'
    attached = plistlib.loads(run('hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', str(image)))
    mounts = [Path(item['mount-point']) for item in attached['system-entities'] if item.get('mount-point')]
    assert mounts, 'DMG did not mount'
    try:
        verify_bundle(mounts[0] / 'LocalMeetingInterpreter.app')
    finally:
        run('hdiutil', 'detach', str(mounts[0]))
    print('Portable ZIP extraction and mounted DMG verification passed.', flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
