#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
APP_DIR="${HARBOR_APP_DIR:-/app}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"
MODE="${EXPO_EVAL_VERIFIER_MODE:-judge}"

mkdir -p "$LOGS_DIR/verifier"

case "$MODE" in
  reference)
    python3 "$TESTS_DIR/reference_check.py" \
      "$APP_DIR" \
      "$TESTS_DIR/reference" \
      "$LOGS_DIR/verifier/reward.json" \
      --details "$LOGS_DIR/verifier/reward-details.json"
    ;;
  judge)
    uv run "$TESTS_DIR/run_rewardkit.py" \
      "$TESTS_DIR/requirements" \
      "$APP_DIR" \
      "$LOGS_DIR/verifier/reward.json"
    ;;
  *)
    echo "Unknown EXPO_EVAL_VERIFIER_MODE: $MODE" >&2
    exit 2
    ;;
esac

cat "$LOGS_DIR/verifier/reward.json"
