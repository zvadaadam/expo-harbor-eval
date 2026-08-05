#!/usr/bin/env bash
# Boot the simulator if needed and reinstall the GoldenLab golden app fresh,
# so every trial starts from a clean data container.
set -euo pipefail

APP_DIR="${HARBOR_APP_DIR:-/app}"
DEVICE="${SIMBENCH_DEVICE:-iPhone 17}"
BUNDLE_ID="com.expo.simbench.goldenlab"

if ! xcrun simctl list devices booted | grep -q "$DEVICE"; then
  xcrun simctl boot "$DEVICE" >/dev/null 2>&1 || true
fi
xcrun simctl bootstatus "$DEVICE" -b >/dev/null

BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/goldenlab-build.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p "$BUILD_DIR/GoldenLab.app"

xcrun -sdk iphonesimulator swiftc \
  -parse-as-library \
  -target arm64-apple-ios16.0-simulator \
  -O \
  "$APP_DIR/app-src/GoldenLab.swift" \
  -o "$BUILD_DIR/GoldenLab.app/GoldenLab"
cp "$APP_DIR/app-src/Info.plist" "$BUILD_DIR/GoldenLab.app/"

xcrun simctl uninstall booted "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl install booted "$BUILD_DIR/GoldenLab.app"

echo "simbench setup complete: $BUNDLE_ID installed on $DEVICE"
