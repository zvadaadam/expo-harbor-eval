from __future__ import annotations

import argparse
import json
from pathlib import Path

from expo_harbor_evals.scoring import normalize_evaluator_result, zero_reward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Expo evaluator result.json")
    parser.add_argument("output", type=Path, help="Harbor reward.json to write")
    parser.add_argument("--details", type=Path, help="Optional details JSON path")
    args = parser.parse_args()

    details = {"ok": True, "errors": [], "input": str(args.input)}
    reward = zero_reward()
    try:
        raw = json.loads(args.input.read_text())
        reward = normalize_evaluator_result(raw)
        details["test_overview"] = raw.get("test_overview")
        details["n_test_plans"] = len(raw.get("test_plans") or [])
    except Exception as exc:
        details["ok"] = False
        details["errors"].append(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reward, indent=2) + "\n")
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        args.details.write_text(json.dumps(details, indent=2) + "\n")
