#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"

mkdir -p "$LOGS_DIR/verifier"
python3 "$TESTS_DIR/verify.py" \
  "$LOGS_DIR/verifier/reward.json" \
  --details "$LOGS_DIR/verifier/details.json"

cat "$LOGS_DIR/verifier/reward.json"
