"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldenlab"


MAX_WRONG_TAPS = 3


def build_checks(container, load_json):
    taps = load_json(container / "Documents/grid-taps.json", [])
    events = load_json(container / "Documents/events.json", [])
    red_tapped = "red" in taps
    wrong_total = sum(color != "red" for color in taps)
    event_ok = any(
        e.get("kind") == "grid-tapped-ui" and str(e.get("title", "")).startswith("red@")
        for e in events
    )
    checks = [
        {"name": "the red square was tapped", "passed": red_tapped},
        {"name": f"at most {MAX_WRONG_TAPS} wrong squares tapped in total",
         "passed": wrong_total <= MAX_WRONG_TAPS,
         "notes": f"{wrong_total} wrong taps" if wrong_total else None},
        {"name": "tap has a matching grid-tapped-ui journal event", "passed": event_ok},
    ]
    extra = {
        "sim_red_tapped": 1.0 if red_tapped else 0.0,
        "sim_wrong_taps": float(wrong_total),
        "sim_ui_event_found": 1.0 if event_ok else 0.0,
    }
    return checks, extra, {"taps": taps, "events": events}



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-06-goldenlab-vision-grid')
