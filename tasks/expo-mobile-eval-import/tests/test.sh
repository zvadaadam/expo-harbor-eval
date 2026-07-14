#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"
OUT_DIR="$LOGS_DIR/verifier/mobile-eval"
mkdir -p "$OUT_DIR"

RESULT_PATH="${EVAL_RESULT_PATH:-$TESTS_DIR/fixtures/evaluator-result-6of6.json}"
if [[ "$RESULT_PATH" == /tests/* && -n "${HARBOR_TESTS_DIR:-}" ]]; then
  RESULT_PATH="$HARBOR_TESTS_DIR/${RESULT_PATH#/tests/}"
fi

if [[ -n "${MOBILE_EVAL_COMMAND:-}" ]]; then
  export MOBILE_EVAL_OUT_DIR="$OUT_DIR"
  bash -lc "$MOBILE_EVAL_COMMAND" > "$OUT_DIR/command-stdout.txt" 2> "$OUT_DIR/command-stderr.txt" || true
  if [[ -z "${EVAL_RESULT_PATH:-}" ]]; then
    RESULT_PATH="$OUT_DIR/result.json"
  fi
fi

python3 "$TESTS_DIR/score_result.py" \
  "$RESULT_PATH" \
  "$LOGS_DIR/verifier/reward.json" \
  --details "$OUT_DIR/details.json"

cat "$LOGS_DIR/verifier/reward.json"
