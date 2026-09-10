"""State-based verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
UI-event journal checks make injected state score zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldennotes"


TARGET_ITEM = "Item 047"


def build_checks(container, load_json):
    claims = load_json(container / "Documents/claims.json", [])
    events = load_json(container / "Documents/events.json", [])
    claim_found = TARGET_ITEM in claims
    event_found = any(
        e.get("kind") == "claim-item-ui" and e.get("title") == TARGET_ITEM
        for e in events
    )
    checks = [
        {"name": f"{TARGET_ITEM!r} is claimed", "passed": claim_found},
        {"name": "claim has a matching claim-item-ui journal event", "passed": event_found},
    ]
    extra = {
        "sim_claim_found": 1.0 if claim_found else 0.0,
        "sim_ui_event_found": 1.0 if event_found else 0.0,
    }
    return checks, extra, {"claims": claims, "events": events}



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-02-inventory-scroll-claim')
