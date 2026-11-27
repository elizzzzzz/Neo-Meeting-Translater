#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${1:-$PROJECT_ROOT/build/native}"
mkdir -p "$OUTPUT_DIR"
xcrun swiftc -parse-as-library -O -target arm64-apple-macos13.0 \
  -framework ScreenCaptureKit -framework CoreMedia \
  "$PROJECT_ROOT/native/SystemAudioBridge.swift" -o "$OUTPUT_DIR/SystemAudioBridge"
codesign --force --sign - --identifier com.localmeetinginterpreter.system-audio "$OUTPUT_DIR/SystemAudioBridge"
