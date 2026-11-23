#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON_BIN="${MEETING_INTERPRETER_BUILD_PYTHON:-python3}"
ICON_VARIANT="${MEETING_INTERPRETER_ICON_VARIANT:-nmt}"
APP_SIGN_IDENTITY="${MEETING_INTERPRETER_CODESIGN_IDENTITY:-}"
INSTALLER_SIGN_IDENTITY="${MEETING_INTERPRETER_INSTALLER_IDENTITY:-}"
NOTARY_PROFILE="${MEETING_INTERPRETER_NOTARY_PROFILE:-}"
NOTARIZE="${MEETING_INTERPRETER_NOTARIZE:-0}"
case "$ICON_VARIANT" in
  nmt) ICON_PATH="assets/icons/nmt.icns" ;;
  a|b|c) ICON_PATH="assets/icons/variant-${ICON_VARIANT}.icns" ;;
  *) echo "MEETING_INTERPRETER_ICON_VARIANT must be nmt, a, b, or c" >&2; exit 2 ;;
esac
# Build outside cloud-managed Documents to avoid partially materialized bundles.
STAGING_DIR="$(mktemp -d /private/tmp/local-meeting-interpreter.XXXXXX)"
PYTHON_CMD=(/usr/bin/arch -arm64 "$PYTHON_BIN")
APP_VERSION="$("${PYTHON_CMD[@]}" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
trap 'rm -rf "$STAGING_DIR"' EXIT

"${PYTHON_CMD[@]}" -c 'import PyInstaller, AppKit, WebKit, mlx_whisper, sherpa_onnx'
bash scripts/build_apple_speech.sh "$STAGING_DIR/native"
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
  --add-data "$PROJECT_ROOT/LICENSE:legal" \
  --add-data "$PROJECT_ROOT/NOTICE:legal" \
  --add-data "$PROJECT_ROOT/THIRD_PARTY_NOTICES.md:legal" \
  --add-binary "$STAGING_DIR/native/AppleSpeechBridge:native" \
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
plutil -replace NSSpeechRecognitionUsageDescription \
  -string "使用 Apple 本机语音识别生成会议原文，音频不上传到云端。" \
  "$BUNDLE/Contents/Info.plist"
plutil -replace CFBundleName -string "NMT" "$BUNDLE/Contents/Info.plist"
plutil -replace CFBundleDisplayName -string "NMT" "$BUNDLE/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$APP_VERSION" "$BUNDLE/Contents/Info.plist"
# The standalone COLLECT directory is already copied into the self-contained
# bundle; release it before making the clean delivery copy on a small disk.
rm -rf "$STAGING_DIR/frozen/LocalMeetingInterpreter" "$STAGING_DIR/work"
mkdir -p "$STAGING_DIR/delivery" "$STAGING_DIR/packages"
ditto --noextattr --norsrc "$BUNDLE" "$STAGING_DIR/delivery/NMT.app"
# COLLECT, BUNDLE and the clean delivery copy contain the same libraries.
# Release staging must not keep all three while extracting archives to verify.
rm -rf "$STAGING_DIR/frozen" "$STAGING_DIR/work"
# MLX locates its default GPU library relative to libmlx.dylib. PyInstaller
# moves the dylib to Frameworks and the data to Resources; bridge that layout.
ln -s ../Resources/mlx/lib/mlx.metallib "$STAGING_DIR/delivery/NMT.app/Contents/Frameworks/mlx.metallib"

if [[ -n "$APP_SIGN_IDENTITY" ]]; then
  codesign --force --deep --options runtime --timestamp \
    --sign "$APP_SIGN_IDENTITY" "$STAGING_DIR/delivery/NMT.app"
  SIGNING_STATUS="Developer ID signed"
else
  # A local ad-hoc signature keeps the app runnable during development, but it
  # cannot satisfy Gatekeeper on another Mac. A Developer ID identity and
  # notarization are required for a public download to open without warnings.
  codesign --force --deep --sign - "$STAGING_DIR/delivery/NMT.app"
  SIGNING_STATUS="ad-hoc test signature (not notarized)"
fi
codesign --verify --deep --strict "$STAGING_DIR/delivery/NMT.app"
ditto -c -k --norsrc --noextattr --keepParent \
  "$STAGING_DIR/delivery/NMT.app" "$STAGING_DIR/packages/NMT-portable.zip"
test -s "$STAGING_DIR/packages/NMT-portable.zip"

# A DMG is a disk image, not an installer. Include the conventional
# Applications shortcut so a user can drag the app into /Applications instead
# of accidentally launching a second copy from the mounted image.
ln -s /Applications "$STAGING_DIR/delivery/Applications"
ditto "$PROJECT_ROOT/docs/macos-first-open.txt" "$STAGING_DIR/delivery/Read Me - First Open.txt"
hdiutil create -fs HFS+ -volname "NMT" \
  -srcfolder "$STAGING_DIR/delivery" -ov -format UDZO "$STAGING_DIR/packages/NMT.dmg"
test -s "$STAGING_DIR/packages/NMT.dmg"

# Also produce a real double-click installer. It is unsigned unless an
# installer identity is supplied, but its payload and install destination are
# standard macOS package metadata.
if [[ -n "$INSTALLER_SIGN_IDENTITY" ]]; then
  productbuild --component "$STAGING_DIR/delivery/NMT.app" /Applications \
    --sign "$INSTALLER_SIGN_IDENTITY" "$STAGING_DIR/packages/NMT.pkg"
else
  productbuild --component "$STAGING_DIR/delivery/NMT.app" /Applications \
    "$STAGING_DIR/packages/NMT.pkg"
fi
test -s "$STAGING_DIR/packages/NMT.pkg"

if [[ "$NOTARIZE" == "1" ]]; then
  if [[ -z "$APP_SIGN_IDENTITY" || -z "$INSTALLER_SIGN_IDENTITY" || -z "$NOTARY_PROFILE" ]]; then
    echo "MEETING_INTERPRETER_NOTARIZE=1 requires application identity, installer identity and MEETING_INTERPRETER_NOTARY_PROFILE" >&2
    exit 2
  fi
  xcrun notarytool submit "$STAGING_DIR/packages/NMT.dmg" \
    --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$STAGING_DIR/packages/NMT.dmg"
  xcrun notarytool submit "$STAGING_DIR/packages/NMT.pkg" \
    --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$STAGING_DIR/packages/NMT.pkg"
fi
"${PYTHON_CMD[@]}" scripts/verify_macos_release.py "$STAGING_DIR/packages"
# Keep checksums paired with the actual archives on every rebuild.
(
  cd "$STAGING_DIR/packages"
  shasum -a 256 NMT-portable.zip NMT.dmg NMT.pkg > "NMT-$APP_VERSION.sha256"
)
# Publish only after extracting the ZIP and mounting the DMG both succeed.
mkdir -p "$PROJECT_ROOT/dist"
ditto "$STAGING_DIR/packages/NMT-portable.zip" "$PROJECT_ROOT/dist/NMT-portable.zip"
ditto "$STAGING_DIR/packages/NMT.dmg" "$PROJECT_ROOT/dist/NMT.dmg"
ditto "$STAGING_DIR/packages/NMT.pkg" "$PROJECT_ROOT/dist/NMT.pkg"
ditto "$STAGING_DIR/packages/NMT-$APP_VERSION.sha256" "$PROJECT_ROOT/dist/NMT-$APP_VERSION.sha256"
ditto "$PROJECT_ROOT/docs/macos-first-open.txt" "$PROJECT_ROOT/dist/Read Me - First Open.txt"
# Keep the direct-open artifact current too; previous releases are retained.
RELEASE_DIR="$HOME/Library/Application Support/LocalMeetingInterpreter/releases/$APP_VERSION"
mkdir -p "$RELEASE_DIR"
ditto --noextattr --norsrc "$STAGING_DIR/delivery/NMT.app" "$RELEASE_DIR/NMT.app"
codesign --verify --deep --strict "$RELEASE_DIR/NMT.app"
"${PYTHON_CMD[@]}" - "$PROJECT_ROOT/dist/NMT.app" "$RELEASE_DIR/NMT.app" <<'PY'
import sys
from pathlib import Path
shortcut, app = map(Path, sys.argv[1:])
if shortcut.is_symlink():
    shortcut.unlink()
if not shortcut.exists():
    shortcut.symlink_to(app, target_is_directory=True)
PY
echo "Built and verified: $PROJECT_ROOT/dist/NMT-portable.zip"
echo "Built and verified: $PROJECT_ROOT/dist/NMT.dmg"
echo "Built and verified: $PROJECT_ROOT/dist/NMT.pkg"
echo "Signing: $SIGNING_STATUS"
if [[ "$NOTARIZE" == "1" ]]; then
  echo "Notarization: stapled"
else
  echo "Notarization: not requested"
fi
