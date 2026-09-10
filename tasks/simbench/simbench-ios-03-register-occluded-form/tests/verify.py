"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldennotes"


TARGET_NAME = "Ada Lovelace"
TARGET_CODE = "EXPO-7431"


def build_checks(container, load_json):
    registration = load_json(container / "Documents/registration.json", {})
    events = load_json(container / "Documents/events.json", [])
    values_ok = (
        registration.get("name") == TARGET_NAME
        and registration.get("code") == TARGET_CODE
    )
    event_found = any(
        e.get("kind") == "register-ui"
        and e.get("title") == f"{TARGET_NAME}|{TARGET_CODE}"
        for e in events
    )
    checks = [
        {"name": "registration has the exact name and code", "passed": values_ok,
         "notes": f"got {registration!r}" if not values_ok else None},
        {"name": "registration has a matching register-ui journal event", "passed": event_found},
    ]
    extra = {
        "sim_registration_ok": 1.0 if values_ok else 0.0,
        "sim_ui_event_found": 1.0 if event_found else 0.0,
    }
    return checks, extra, {"registration": registration, "events": events}



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-03-register-occluded-form')
