#!/usr/bin/env bash
set -euo pipefail

SOLUTION_DIR="${HARBOR_SOLUTION_DIR:-/solution}"
APP_DIR="${HARBOR_APP_DIR:-/app}"

cp -R "$SOLUTION_DIR/reference/." "$APP_DIR/"
