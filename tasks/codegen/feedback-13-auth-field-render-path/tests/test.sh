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
  mobile)
    # Opt-in candidate-app verification. This command is supplied by the
    # installed evaluator harness, never by the candidate workspace.
    if [[ ! -f "$TESTS_DIR/requirements/runtime.json" ]]; then
      echo "No native scenario for this task" >&2
      exit 2
    fi
    set +e
    expo-mobile-eval run --task-file "$TESTS_DIR/requirements/runtime.json" \
      --candidate "$APP_DIR" --output "$LOGS_DIR/verifier/mobile-eval"
    status=$?
    set -e
    if [[ -f "$LOGS_DIR/verifier/mobile-eval/reward.json" ]]; then
      cp "$LOGS_DIR/verifier/mobile-eval/reward.json" "$LOGS_DIR/verifier/reward.json"
      cp "$LOGS_DIR/verifier/mobile-eval/details.json" "$LOGS_DIR/verifier/details.json"
    fi
    if (( status > 1 )); then exit "$status"; fi
    ;;
  *)
    echo "Unknown EXPO_EVAL_VERIFIER_MODE: $MODE" >&2
    exit 2
    ;;
esac

cat "$LOGS_DIR/verifier/reward.json"
