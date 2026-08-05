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


TARGET = 72


def build_checks(container, load_json):
    settings = load_json(container / "Documents/settings.json", {})
    events = load_json(container / "Documents/events.json", [])
    value_ok = settings.get("temperature") == TARGET
    event_ok = any(
        e.get("kind") == "save-temperature-ui" and e.get("title") == str(TARGET)
        for e in events
    )
    checks = [
        {"name": f"saved temperature is exactly {TARGET}", "passed": value_ok,
         "notes": f"got {settings.get('temperature')!r}" if not value_ok else None},
        {"name": "save has a matching save-temperature-ui journal event", "passed": event_ok},
    ]
    extra = {
        "sim_value_ok": 1.0 if value_ok else 0.0,
        "sim_ui_event_found": 1.0 if event_ok else 0.0,
    }
    return checks, extra, {"settings": settings, "events": events}


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
