#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${MEETING_INTERPRETER_BUILD_PYTHON:-python3}"
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/local-meeting-interpreter.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT

"$PYTHON_BIN" -m pip install -e '.[installer]'
rm -rf build dist
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --windowed \
  --name "LocalMeetingInterpreter" \
  --add-data "web:web" \
  --exclude-module "torch" \
  --exclude-module "transformers" \
  --exclude-module "pyannote" \
  --exclude-module "cv2" \
  --exclude-module "pandas" \
  --exclude-module "matplotlib" \
  --exclude-module "PIL" \
  --exclude-module "datasets" \
  --exclude-module "spacy" \
  --exclude-module "thinc" \
  --exclude-module "onnxruntime" \
  --exclude-module "httptools" \
  --exclude-module "uvloop" \
  --exclude-module "watchfiles" \
  --exclude-module "tkinter" \
  --exclude-module "websockets.speedups" \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.protocols.http.h11_impl" \
  --hidden-import "uvicorn.protocols.websockets.websockets_impl" \
  --hidden-import "mlx_whisper" \
  --collect-all "mlx_whisper" \
  --collect-all "mlx" \
  src/meeting_interpreter/desktop.py

# macOS may attribute browser microphone access to the launching desktop app.
# Keep an explicit purpose string in the bundle so TCC never treats the app as
# a privacy-sensitive caller without a usage description.
plutil -replace NSMicrophoneUsageDescription \
  -string "用于采集本地麦克风或会议回环音频，并在本机生成实时字幕。" \
  "dist/LocalMeetingInterpreter.app/Contents/Info.plist"

if command -v hdiutil >/dev/null 2>&1; then
  ditto --noextattr --norsrc "dist/LocalMeetingInterpreter.app" "$STAGING_DIR/LocalMeetingInterpreter.app"
  codesign --force --deep --sign - "$STAGING_DIR/LocalMeetingInterpreter.app"
  codesign --verify --deep --strict "$STAGING_DIR/LocalMeetingInterpreter.app"
  hdiutil create -volname "Local Meeting Interpreter" -srcfolder "$STAGING_DIR" -ov -format UDZO "dist/LocalMeetingInterpreter.dmg"
fi

echo "Built: $PROJECT_ROOT/dist/LocalMeetingInterpreter.app"
if [ -f "$PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg" ]; then
  echo "Built: $PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg"
fi
