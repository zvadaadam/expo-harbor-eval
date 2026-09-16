"""State-based OAuth verifier, no LLM judge.

Emits named binary checks (supabase/evals-style): the reward is 1.0 only when
every check passes, and details.json carries the check list plus raw evidence.
A sign-in counts only when the app-side session, the ordered UI-event journal,
and the in-app identity provider's own PKCE-bound record all agree — so a
session file written directly into the container (no provider authorization,
no consent, no matching journal) scores zero.
"""

from __future__ import annotations


BUNDLE_ID = "com.expo.simbench.goldengate"

MODE = 'system'
USERNAME = 'riley.chen'


def _subsequence(events, steps) -> bool:
    pointer = 0
    for event in events:
        if pointer < len(steps) and (event.get("kind"), event.get("title")) == steps[pointer]:
            pointer += 1
    return pointer == len(steps)


def build_checks(container, load_json):
    session = load_json(container / "Documents/session.json", {})
    events = load_json(container / "Documents/events.json", [])
    provider = load_json(container / "Documents/provider.json", {})

    session_ok = (
        session.get("username") == USERNAME
        and session.get("mode") == MODE
        and bool(session.get("accessToken"))
        and bool(session.get("pairingCode"))
    )

    requests = provider.get("requests") or {}
    matching = [request_id for request_id, r in requests.items() if (
        r.get("username") == USERNAME
        and r.get("consent") == "allow"
        and bool(r.get("accessToken"))
        and r.get("accessToken") == session.get("accessToken")
        and bool(r.get("pairingCode"))
        and r.get("pairingCode") == session.get("pairingCode")
        and bool(r.get("code"))
        and bool(r.get("codeChallenge"))
    )]
    provider_ok = bool(matching)

    def login_steps(request_id):
        return [("sign-in-started-ui", MODE), ("provider-authorize", request_id),
                ("provider-login-accepted", f"{request_id}|{USERNAME}")]

    # Token, pairing code and every provider event must belong to one request.
    # Independent successful fragments from different attempts are insufficient.
    journal_ok = any(_subsequence(events, login_steps(request_id) + [
        ("provider-consent-granted", f"{request_id}|{USERNAME}"),
        ("callback-received", f"{MODE}|ok"),
        ("provider-token-issued", f"{request_id}|{USERNAME}"),
        ("provider-userinfo", f"{request_id}|{USERNAME}"),
        ("signed-in", f"{USERNAME}|{MODE}"),
    ]) for request_id in matching)
    denied_ok = not session and any(
        r.get("username") == USERNAME and r.get("consent") == "deny"
        and not r.get("accessToken") and _subsequence(events, login_steps(request_id) + [
            ("provider-consent-denied", f"{request_id}|{USERNAME}"),
        ]) for request_id, r in requests.items()
    )

    checks = [
        {"name": f"session records {USERNAME!r} signed in via the {MODE} surface", "passed": session_ok},
        {"name": "UI-event journal shows one request's sign-in steps in order", "passed": journal_ok},
        {"name": "provider issued this session's token and pairing code after consent", "passed": provider_ok},
    ]
    extra = {
        "sim_oauth_signed_in": 1.0 if session_ok else 0.0,
        "sim_oauth_journal_ok": 1.0 if journal_ok else 0.0,
        "sim_oauth_provider_ok": 1.0 if provider_ok else 0.0,
        "sim_oauth_consent_denied": 1.0 if denied_ok else 0.0,
    }
    evidence = {"session": session, "events": events, "provider": provider}
    return checks, extra, evidence



if __name__ == "__main__":
    from simbench_evidence import verifier_main

    verifier_main(BUNDLE_ID, build_checks, 'simbench-ios-09-goldengate-system-auth-session')
