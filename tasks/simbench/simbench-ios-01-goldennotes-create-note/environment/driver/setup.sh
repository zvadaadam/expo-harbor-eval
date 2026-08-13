#!/usr/bin/env bash
# Idempotent per-trial setup: boot the simulator, build the golden app from
# source, and install it fresh (uninstall first so the data container starts
# clean). Run via the task healthcheck before the agent phase.
set -euo pipefail

DEVICE="${SIMBENCH_DEVICE:-iPhone 17}"
BUNDLE_ID="com.expo.simbench.goldennotes"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${TMPDIR:-/tmp}/simbench-goldennotes-build"

if ! xcrun simctl list devices booted | grep -q "Booted"; then
  xcrun simctl boot "$DEVICE"
fi
xcrun simctl bootstatus "$DEVICE" -b >/dev/null 2>&1 || true

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/GoldenNotes.app"
xcrun -sdk iphonesimulator swiftc -parse-as-library \
  -target arm64-apple-ios16.0-simulator -O \
  "$APP_DIR/app-src/GoldenNotes.swift" \
  -o "$BUILD_DIR/GoldenNotes.app/GoldenNotes"
cp "$APP_DIR/app-src/Info.plist" "$BUILD_DIR/GoldenNotes.app/"

xcrun simctl uninstall booted "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl install booted "$BUILD_DIR/GoldenNotes.app"
echo "simbench setup complete: $BUNDLE_ID installed on $DEVICE"
