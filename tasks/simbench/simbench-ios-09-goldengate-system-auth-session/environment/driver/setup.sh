#!/usr/bin/env bash
# The Harbor environment owns device creation and cleanup. All operations
# target its explicit device; this script only installs a fresh golden app.
set -euo pipefail
DEVICE="${SIMBENCH_DEVICE:?Run with SimbenchEnvironment or set an explicit simulator UDID}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME=$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$APP_DIR/app-src/Info.plist")
BUNDLE_ID=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP_DIR/app-src/Info.plist")
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/simbench-build.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
xcrun simctl bootstatus "$DEVICE" -b >/dev/null
mkdir -p "$BUILD_DIR/$NAME.app"
xcrun -sdk iphonesimulator swiftc -parse-as-library \
  -target arm64-apple-ios16.0-simulator -O \
  "$APP_DIR/app-src/$NAME.swift" -o "$BUILD_DIR/$NAME.app/$NAME"
cp "$APP_DIR/app-src/Info.plist" "$BUILD_DIR/$NAME.app/"
xcrun simctl uninstall "$DEVICE" "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl install "$DEVICE" "$BUILD_DIR/$NAME.app"
if [[ -n "${HARBOR_LOGS_DIR:-}" ]]; then
  shasum -a 256 "$APP_DIR/app-src/$NAME.swift" "$APP_DIR/app-src/Info.plist" \
    "$BUILD_DIR/$NAME.app/$NAME" > "$HARBOR_LOGS_DIR/artifacts/app-sha256.txt"
fi
echo "simbench setup complete: $BUNDLE_ID installed on $DEVICE"

# Candidate UI interaction does not require golden-app implementation source.
if [[ -n "${HARBOR_LOCAL_ROOT:-}" && "$APP_DIR" == "$HARBOR_LOCAL_ROOT/"* ]]; then
  rm -rf "$APP_DIR/app-src"
fi
