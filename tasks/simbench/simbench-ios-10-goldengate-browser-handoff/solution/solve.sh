#!/usr/bin/env bash
set -euo pipefail

SOLUTION_DIR="${HARBOR_SOLUTION_DIR:-/solution}"
python3 "$SOLUTION_DIR/oracle.py"
