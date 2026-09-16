"""OAuth evidence checks use fabricated records; no simulator or model calls."""

import importlib.util
from pathlib import Path

import pytest

from expo_harbor_evals.simbench_calibrate import check_calibration
from expo_harbor_evals.simbench_evidence import write_json

TASKS = sorted((Path(__file__).resolve().parents[1] / "tasks/simbench").glob("*-goldengate-*"))


@pytest.fixture(params=TASKS, ids=lambda task: task.name)
def verifier(request):
    spec = importlib.util.spec_from_file_location("oauth_verifier", request.param / "tests/verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(verifier, *, consent="allow"):
    user, mode = verifier.USERNAME, verifier.MODE
    provider = {"username": user, "state": "state", "consent": consent,
                "code": "code", "codeChallenge": "challenge",
                "accessToken": "token", "pairingCode": "PAIR-1234"}
    steps = [("sign-in-started-ui", mode), ("provider-authorize", "request-a"),
             ("provider-login-accepted", f"request-a|{user}")]
    if consent == "allow":
        steps += [("provider-consent-granted", f"request-a|{user}"),
                  ("callback-received", f"{mode}|ok"),
                  ("provider-token-issued", f"request-a|{user}"),
                  ("provider-userinfo", f"request-a|{user}"),
                  ("signed-in", f"{user}|{mode}")]
        session = {"username": user, "mode": mode, "accessToken": "token", "pairingCode": "PAIR-1234"}
    else:
        steps += [("provider-consent-denied", f"request-a|{user}"),
                  ("callback-received", f"{mode}|error=access_denied")]
        session = {}
        provider.update(code=None, accessToken=None, pairingCode=None)
    return {"session.json": session, "provider.json": {"requests": {"request-a": provider}},
            "events.json": [{"kind": kind, "title": title} for kind, title in steps]}


def check(verifier, files):
    return verifier.build_checks(Path("/fixture"), lambda p, default: files.get(p.name, default))


def test_complete_oauth_request_passes(verifier):
    checks, _, _ = check(verifier, evidence(verifier))
    assert all(row["passed"] for row in checks)


@pytest.mark.parametrize("mutation", ["token", "pairing", "login-request", "consent-request", "token-event"])
def test_mismatched_oauth_records_cannot_pass(verifier, mutation):
    files = evidence(verifier)
    if mutation in ("token", "pairing"):
        key = "accessToken" if mutation == "token" else "pairingCode"
        files["session.json"][key] = "does-not-match-provider"
    elif mutation == "token-event":
        files["events.json"] = [e for e in files["events.json"] if e["kind"] != "provider-token-issued"]
    else:
        kind = "provider-login-accepted" if mutation == "login-request" else "provider-consent-granted"
        next(e for e in files["events.json"] if e["kind"] == kind)["title"] = "request-b|" + verifier.USERNAME
    checks, _, _ = check(verifier, files)
    assert not all(row["passed"] for row in checks)


def test_consent_denial_requires_actual_login_and_denial(verifier):
    files = evidence(verifier, consent="deny")
    checks, extra, _ = check(verifier, files)
    assert not all(row["passed"] for row in checks)
    assert extra["sim_oauth_consent_denied"] == 1
    _, extra, _ = check(verifier, {})
    assert extra["sim_oauth_consent_denied"] == 0
    files["events.json"] = [e for e in files["events.json"] if e["kind"] != "provider-login-accepted"]
    _, extra, _ = check(verifier, files)
    assert extra["sim_oauth_consent_denied"] == 0


def test_consent_calibration_rejects_unopened_app_zero(tmp_path):
    for condition, reward in (("nop", 0), ("oracle", 1), ("consent-denied", 0)):
        write_json(tmp_path / condition / "result.json", {
            "agent_info": {"name": "nop" if condition == "nop" else "oracle",
                           "model_info": {"name": condition}},
            "verifier_result": {"rewards": {"reward": reward, "sim_runner_ok": 1,
                "sim_oauth_signed_in": reward, "sim_oauth_consent_denied": 0}}})
    assert not check_calibration(tmp_path, 1, False, ["consent-denied"])["ok"]
    import json
    path = tmp_path / "consent-denied/result.json"
    record = json.loads(path.read_text())
    record["verifier_result"]["rewards"]["sim_oauth_consent_denied"] = 1
    write_json(path, record)
    assert check_calibration(tmp_path, 1, False, ["consent-denied"])["ok"]
