#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--details", type=Path, required=True)
    args = parser.parse_args()

    details: dict[str, Any] = {"ok": True, "errors": [], "input": str(args.input)}
    reward = zero_reward()
    try:
        raw = json.loads(args.input.read_text())
        reward = normalize(raw)
        details["test_overview"] = raw.get("test_overview")
        details["n_test_plans"] = len(raw.get("test_plans") or [])
    except Exception as exc:
        details["ok"] = False
        details["errors"].append(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reward, indent=2) + "\n")
    args.details.parent.mkdir(parents=True, exist_ok=True)
    args.details.write_text(json.dumps(details, indent=2) + "\n")


def normalize(raw: dict[str, Any]) -> dict[str, float]:
    score = num(raw.get("score"))
    full_points = num(raw.get("full_points"))
    macro_pct = num(raw.get("macro_avg_pct"))
    micro_pct = num(raw.get("micro_pct"))
    reward = score / full_points if full_points > 0 else macro_pct / 100.0
    return {
        "reward": clamp(reward),
        "mobile_score": score,
        "mobile_full_points": full_points,
        "mobile_macro": macro_pct / 100.0,
        "mobile_micro": micro_pct / 100.0,
        "mobile_not_applicable": num(raw.get("n_not_applicable")),
        "mobile_runner_ok": 1.0,
    }


def zero_reward() -> dict[str, float]:
    return {
        "reward": 0.0,
        "mobile_score": 0.0,
        "mobile_full_points": 0.0,
        "mobile_macro": 0.0,
        "mobile_micro": 0.0,
        "mobile_not_applicable": 0.0,
        "mobile_runner_ok": 0.0,
    }


def num(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


if __name__ == "__main__":
    main()
