#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -m pip install -e '.[installer]'
rm -rf build dist
pyinstaller --noconfirm --clean --windowed \
  --name "LocalMeetingInterpreter" \
  --add-data "web:web" \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.loops.auto" \
  --hidden-import "uvicorn.protocols.http.auto" \
  --hidden-import "uvicorn.protocols.websockets.auto" \
  src/meeting_interpreter/desktop.py

if command -v hdiutil >/dev/null 2>&1; then
  hdiutil create -volname "Local Meeting Interpreter" -srcfolder "dist/LocalMeetingInterpreter.app" -ov -format UDZO "dist/LocalMeetingInterpreter.dmg"
fi

echo "Built: $PROJECT_ROOT/dist/LocalMeetingInterpreter.app"
if [ -f "$PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg" ]; then
  echo "Built: $PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg"
fi
