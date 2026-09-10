"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldenlab"


def build_checks(container, load_json):
    submission = load_json(container / "Documents/submission.json", {})
    events = load_json(container / "Documents/events.json", [])
    revealed = [e.get("title") for e in events if e.get("kind") == "code-revealed"]
    submitted = submission.get("submitted")
    submit_events = [
        e.get("title") for e in events if e.get("kind") == "code-submitted-ui"
    ]
    restarts = sum(1 for e in events if e.get("kind") == "reveal-restarted")
    match = bool(submitted) and bool(revealed) and submitted == revealed[-1]
    event_ok = bool(submit_events) and submit_events[-1] == submitted
    checks = [
        {"name": "a code was revealed through the UI", "passed": bool(revealed)},
        {"name": "submitted code matches the last revealed code", "passed": match,
         "notes": f"submitted={submitted!r} revealed={revealed[-1:]!r}" if not match else None},
        {"name": "submission has a matching code-submitted-ui journal event", "passed": event_ok},
    ]
    extra = {
        "sim_code_match": 1.0 if match else 0.0,
        "sim_ui_event_found": 1.0 if event_ok else 0.0,
        "sim_reveal_restarts": float(restarts),
    }
    return checks, extra, {"submission": submission, "revealed": revealed, "events": events}



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-05-goldenlab-reveal-code')
