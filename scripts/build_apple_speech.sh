#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${1:-$PROJECT_ROOT/build/native}"
mkdir -p "$OUTPUT_DIR"
xcrun swiftc -parse-as-library -O -target arm64-apple-macos14.0 \
  -module-cache-path "${TMPDIR:-/private/tmp}/lmi-swift-module-cache" \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist \
  -Xlinker "$PROJECT_ROOT/native/AppleSpeechBridge-Info.plist" \
  "$PROJECT_ROOT/native/AppleSpeechBridge.swift" -o "$OUTPUT_DIR/AppleSpeechBridge"
SPEECH_SIGN_IDENTITY="${MEETING_INTERPRETER_CODESIGN_IDENTITY:--}"
if [[ "$SPEECH_SIGN_IDENTITY" == "-" ]]; then
  codesign --force --sign - --identifier com.localmeetinginterpreter.speech "$OUTPUT_DIR/AppleSpeechBridge"
else
  codesign --force --options runtime --timestamp \
    --sign "$SPEECH_SIGN_IDENTITY" --identifier com.localmeetinginterpreter.speech \
    "$OUTPUT_DIR/AppleSpeechBridge"
fi
