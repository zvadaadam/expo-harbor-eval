"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BUNDLE_ID = "com.expo.simbench.goldenlab"


MAX_WRONG_TAPS = 3


def build_checks(container, load_json):
    taps = load_json(container / "Documents/grid-taps.json", [])
    events = load_json(container / "Documents/events.json", [])
    red_tapped = "red" in taps
    wrong_before = 0
    for color in taps:
        if color == "red":
            break
        wrong_before += 1
    event_ok = any(
        e.get("kind") == "grid-tapped-ui" and str(e.get("title", "")).startswith("red@")
        for e in events
    )
    checks = [
        {"name": "the red square was tapped", "passed": red_tapped},
        {"name": f"at most {MAX_WRONG_TAPS} wrong squares tapped first",
         "passed": wrong_before <= MAX_WRONG_TAPS,
         "notes": f"{wrong_before} wrong taps" if wrong_before else None},
        {"name": "tap has a matching grid-tapped-ui journal event", "passed": event_ok},
    ]
    extra = {
        "sim_red_tapped": 1.0 if red_tapped else 0.0,
        "sim_wrong_taps": float(wrong_before),
        "sim_ui_event_found": 1.0 if event_ok else 0.0,
    }
    return checks, extra, {"taps": taps, "events": events}


def app_container() -> Path | None:
    completed = subprocess.run(
        ["xcrun", "simctl", "get_app_container", "booted", BUNDLE_ID, "data"],
        capture_output=True, text=True, timeout=60,
    )
    if completed.returncode != 0:
        return None
    return Path(completed.stdout.strip())


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reward", type=Path)
    parser.add_argument("--details", type=Path)
    args = parser.parse_args()

    container = app_container()
    if container is None:
        checks = [{"name": "app installed in simulator", "passed": False}]
        extra, evidence = {}, {}
    else:
        checks, extra, evidence = build_checks(container, load_json)
        checks.insert(0, {"name": "app installed in simulator", "passed": True})

    reward = 1.0 if all(c["passed"] for c in checks) else 0.0
    result = {"reward": reward, **extra}
    args.reward.parent.mkdir(parents=True, exist_ok=True)
    args.reward.write_text(json.dumps(result, indent=2) + "\n")
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        args.details.write_text(
            json.dumps({"checks": checks, "evidence": evidence}, indent=2, default=str)
            + "\n"
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
