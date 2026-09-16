#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ID="${1:-com.expo.simbench.goldengate}"
xcrun simctl terminate "${SIMBENCH_DEVICE:?Set the trial simulator UDID}" "$BUNDLE_ID" >/dev/null 2>&1 || true
xcrun simctl launch "${SIMBENCH_DEVICE:?Set the trial simulator UDID}" "$BUNDLE_ID"
