#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ID="${1:-com.expo.simbench.goldennotes}"
xcrun simctl terminate booted "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl launch booted "$BUNDLE_ID"
