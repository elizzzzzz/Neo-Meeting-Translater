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
  --exclude-module "scipy" \
  --exclude-module "pandas" \
  --exclude-module "matplotlib" \
  --exclude-module "PIL" \
  --exclude-module "numpy" \
  --exclude-module "datasets" \
  --exclude-module "spacy" \
  --exclude-module "thinc" \
  --exclude-module "numba" \
  --exclude-module "llvmlite" \
  --exclude-module "onnxruntime" \
  --exclude-module "httptools" \
  --exclude-module "uvloop" \
  --exclude-module "watchfiles" \
  --exclude-module "tkinter" \
  --exclude-module "websockets.speedups" \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.protocols.http.h11_impl" \
  --hidden-import "uvicorn.protocols.websockets.websockets_impl" \
  src/meeting_interpreter/desktop.py

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
