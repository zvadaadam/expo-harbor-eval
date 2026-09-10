#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-screen.png}"
xcrun simctl io "${SIMBENCH_DEVICE:?Set the trial simulator UDID}" screenshot "$OUT" >/dev/null 2>&1
echo "wrote $OUT"
