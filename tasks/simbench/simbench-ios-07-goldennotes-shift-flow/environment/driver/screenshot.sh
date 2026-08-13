#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-screen.png}"
xcrun simctl io booted screenshot "$OUT" >/dev/null 2>&1
echo "wrote $OUT"
