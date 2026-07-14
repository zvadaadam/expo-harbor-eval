from __future__ import annotations

from typing import Any


def normalize_evaluator_result(raw: dict[str, Any]) -> dict[str, float]:
    """Return Harbor-compatible numeric rewards from Expo evaluator JSON."""
    score = _num(raw.get("score"))
    full_points = _num(raw.get("full_points"))
    macro_pct = _num(raw.get("macro_avg_pct"))
    micro_pct = _num(raw.get("micro_pct"))
    reward = score / full_points if full_points > 0 else macro_pct / 100.0
    return {
        "reward": _clamp(reward),
        "mobile_score": score,
        "mobile_full_points": full_points,
        "mobile_macro": macro_pct / 100.0,
        "mobile_micro": micro_pct / 100.0,
        "mobile_not_applicable": _num(raw.get("n_not_applicable")),
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


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
