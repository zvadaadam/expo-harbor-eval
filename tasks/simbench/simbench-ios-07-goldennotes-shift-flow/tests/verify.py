"""State-based flow verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
Beyond per-step state and journal checks, the flow tier requires the four UI
events to appear as an ordered subsequence of the journal — a correct end
state reached out of order (or injected) scores zero.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BUNDLE_ID = "com.expo.simbench.goldennotes"

NOTE_TITLE = "Shift Opened 007"
CLAIM_ITEMS = ("Item 019", "Item 052")
REGISTER_NAME = "Riley Chen"
REGISTER_CODE = "DOCK-7"

REQUIRED_SEQUENCE = (
    ("add-note-ui", NOTE_TITLE),
    ("claim-item-ui", CLAIM_ITEMS[0]),
    ("claim-item-ui", CLAIM_ITEMS[1]),
    ("register-ui", f"{REGISTER_NAME}|{REGISTER_CODE}"),
)


def build_checks(container, load_json):
    notes = load_json(container / "Documents/notes.json", [])
    claims = load_json(container / "Documents/claims.json", [])
    registration = load_json(container / "Documents/registration.json", {})
    events = load_json(container / "Documents/events.json", [])

    note_ok = any(n.get("title") == NOTE_TITLE for n in notes)
    claims_ok = all(item in claims for item in CLAIM_ITEMS)
    register_ok = (
        registration.get("name") == REGISTER_NAME
        and registration.get("code") == REGISTER_CODE
    )

    def has_event(kind: str, title: str) -> bool:
        return any(
            e.get("kind") == kind and e.get("title") == title for e in events
        )

    journal_ok = all(has_event(kind, title) for kind, title in REQUIRED_SEQUENCE)

    # Ordered-subsequence scan: each required step must appear after the
    # previous one somewhere in the journal (retries in between are fine).
    pointer = 0
    for event in events:
        if pointer < len(REQUIRED_SEQUENCE) and (
            event.get("kind"),
            event.get("title"),
        ) == REQUIRED_SEQUENCE[pointer]:
            pointer += 1
    order_ok = pointer == len(REQUIRED_SEQUENCE)

    checks = [
        {"name": f"note titled {NOTE_TITLE!r} exists", "passed": note_ok},
        {"name": "both inventory items claimed", "passed": claims_ok},
        {"name": "registration matches name and code", "passed": register_ok},
        {"name": "every step has a matching UI journal event", "passed": journal_ok},
        {"name": "journal shows the four steps in order", "passed": order_ok},
    ]
    extra = {
        "sim_flow_state_complete": 1.0 if (note_ok and claims_ok and register_ok) else 0.0,
        "sim_flow_steps_in_order": 1.0 if order_ok else 0.0,
    }
    evidence = {
        "notes": notes,
        "claims": claims,
        "registration": registration,
        "events": events,
    }
    return checks, extra, evidence


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
