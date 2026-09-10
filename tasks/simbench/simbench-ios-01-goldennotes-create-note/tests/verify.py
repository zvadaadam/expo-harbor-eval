"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldennotes"


TARGET_TITLE = "Harbor Sim Bench 001"


def build_checks(container, load_json):
    notes = load_json(container / "Documents/notes.json", [])
    events = load_json(container / "Documents/events.json", [])
    note_found = any(n.get("title") == TARGET_TITLE for n in notes)
    event_found = any(
        e.get("kind") == "add-note-ui" and e.get("title") == TARGET_TITLE
        for e in events
    )
    checks = [
        {"name": f"note titled {TARGET_TITLE!r} exists", "passed": note_found},
        {"name": "note has a matching add-note-ui journal event", "passed": event_found},
    ]
    extra = {
        "sim_note_found": 1.0 if note_found else 0.0,
        "sim_ui_event_found": 1.0 if event_found else 0.0,
    }
    return checks, extra, {"notes": notes, "events": events}



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-01-goldennotes-create-note')
