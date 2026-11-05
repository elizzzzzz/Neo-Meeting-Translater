#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${MEETING_INTERPRETER_BUILD_PYTHON:-python3}"
ICON_VARIANT="${MEETING_INTERPRETER_ICON_VARIANT:-a}"
case "$ICON_VARIANT" in
  a|b|c) ICON_PATH="assets/icons/variant-${ICON_VARIANT}.icns" ;;
  *) echo "MEETING_INTERPRETER_ICON_VARIANT must be a, b, or c" >&2; exit 2 ;;
esac
# Build outside cloud-managed Documents to avoid partially materialized bundles.
STAGING_DIR="$(mktemp -d /private/tmp/local-meeting-interpreter.XXXXXX)"
PYTHON_CMD=(/usr/bin/arch -arm64 "$PYTHON_BIN")
trap 'rm -rf "$STAGING_DIR"' EXIT

"${PYTHON_CMD[@]}" -c 'import PyInstaller, AppKit, WebKit, mlx_whisper, sherpa_onnx'
"${PYTHON_CMD[@]}" -m PyInstaller --noconfirm --clean --windowed \
  --distpath "$STAGING_DIR/frozen" \
  --workpath "$STAGING_DIR/work" \
  --specpath "$STAGING_DIR" \
  --target-architecture arm64 \
  --osx-bundle-identifier "com.localmeetinginterpreter.app" \
  --name "LocalMeetingInterpreter" \
  --paths "$PROJECT_ROOT/src" \
  --icon "$PROJECT_ROOT/$ICON_PATH" \
  --add-data "$PROJECT_ROOT/web:web" \
  --exclude-module "torch" \
  --exclude-module "transformers" \
  --exclude-module "pyannote" \
  --exclude-module "cv2" \
  --exclude-module "pandas" \
  --exclude-module "matplotlib" \
  --exclude-module "PIL" \
  --exclude-module "datasets" \
  --exclude-module "jax" \
  --exclude-module "jaxlib" \
  --exclude-module "pyarrow" \
  --exclude-module "sklearn" \
  --exclude-module "tensorflow" \
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
  --hidden-import "AppKit" \
  --hidden-import "WebKit" \
  --hidden-import "Foundation" \
  --hidden-import "objc" \
  --hidden-import "mlx_whisper" \
  --collect-all "mlx_whisper" \
  --collect-all "mlx" \
  --collect-all "sherpa_onnx" \
  "$PROJECT_ROOT/src/meeting_interpreter/desktop.py"

BUNDLE="$STAGING_DIR/frozen/LocalMeetingInterpreter.app"
plutil -replace NSMicrophoneUsageDescription \
  -string "用于采集本地麦克风或会议回环音频，并在本机生成实时字幕。" \
  "$BUNDLE/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "0.2.6" "$BUNDLE/Contents/Info.plist"
# The standalone COLLECT directory is already copied into the self-contained
# bundle; release it before making the clean delivery copy on a small disk.
rm -rf "$STAGING_DIR/frozen/LocalMeetingInterpreter" "$STAGING_DIR/work"
mkdir -p "$STAGING_DIR/delivery" "$STAGING_DIR/packages"
ditto --noextattr --norsrc "$BUNDLE" "$STAGING_DIR/delivery/LocalMeetingInterpreter.app"
# COLLECT, BUNDLE and the clean delivery copy contain the same libraries.
# Release staging must not keep all three while extracting archives to verify.
rm -rf "$STAGING_DIR/frozen" "$STAGING_DIR/work"
# MLX locates its default GPU library relative to libmlx.dylib. PyInstaller
# moves the dylib to Frameworks and the data to Resources; bridge that layout.
ln -s ../Resources/mlx/lib/mlx.metallib "$STAGING_DIR/delivery/LocalMeetingInterpreter.app/Contents/Frameworks/mlx.metallib"
codesign --force --deep --sign - "$STAGING_DIR/delivery/LocalMeetingInterpreter.app"
codesign --verify --deep --strict "$STAGING_DIR/delivery/LocalMeetingInterpreter.app"
ditto -c -k --norsrc --noextattr --keepParent \
  "$STAGING_DIR/delivery/LocalMeetingInterpreter.app" "$STAGING_DIR/packages/LocalMeetingInterpreter-portable.zip"
test -s "$STAGING_DIR/packages/LocalMeetingInterpreter-portable.zip"
hdiutil create -fs HFS+ -volname "Local Meeting Interpreter" \
  -srcfolder "$STAGING_DIR/delivery" -ov -format UDZO "$STAGING_DIR/packages/LocalMeetingInterpreter.dmg"
test -s "$STAGING_DIR/packages/LocalMeetingInterpreter.dmg"
"${PYTHON_CMD[@]}" scripts/verify_macos_release.py "$STAGING_DIR/packages"
# Publish only after extracting the ZIP and mounting the DMG both succeed.
mkdir -p "$PROJECT_ROOT/dist"
ditto "$STAGING_DIR/packages/LocalMeetingInterpreter-portable.zip" "$PROJECT_ROOT/dist/LocalMeetingInterpreter-portable.zip"
ditto "$STAGING_DIR/packages/LocalMeetingInterpreter.dmg" "$PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg"
echo "Built and verified: $PROJECT_ROOT/dist/LocalMeetingInterpreter-portable.zip"
echo "Built and verified: $PROJECT_ROOT/dist/LocalMeetingInterpreter.dmg"
