"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


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



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-04-goldenlab-dial-precision')
