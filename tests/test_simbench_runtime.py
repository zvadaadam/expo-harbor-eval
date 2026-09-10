from __future__ import annotations

import importlib.util
import asyncio
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from expo_harbor_evals import simbench_evidence as evidence
from expo_harbor_evals.simbench_calibrate import FLOW_TASK, check_calibration
from expo_harbor_evals.simbench_calibrate import cleanup_devices
from expo_harbor_evals.local_env import LocalHostEnvironment
from expo_harbor_evals.report import load_runs, build_series

REPO = Path(__file__).resolve().parents[1]
BUNDLE = "com.expo.simbench.goldennotes"
IDENTITY = dict(bundle_id=BUNDLE, task_id=FLOW_TASK, trial_id="test-trial")


def flow_module():
    path = REPO / "tasks/simbench" / FLOW_TASK / "tests/verify.py"
    spec = importlib.util.spec_from_file_location("flow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_snapshot(tmp_path, state=None):
    container = tmp_path / "app"
    (container / "Documents").mkdir(parents=True)
    for name, value in (state or {}).items():
        evidence.write_json(container / "Documents" / name, value)
    root = tmp_path / "evidence"
    evidence.snapshot(container, root, **IDENTITY, device="udid", backend="local-macos")
    return root


def ordered_state():
    m = flow_module()
    return {"notes.json": [{"title": m.NOTE_TITLE}], "claims.json": list(m.CLAIM_ITEMS),
            "registration.json": {"name": m.REGISTER_NAME, "code": m.REGISTER_CODE},
            "events.json": [{"kind": kind, "title": title} for kind, title in m.REQUIRED_SEQUENCE]}


@pytest.mark.parametrize("condition,expected", [("empty", 0), ("ordered", 1), ("wrong-order", 0), ("injected", 0)])
def test_portable_flow_preserves_brackets(tmp_path, condition, expected):
    state = {} if condition == "empty" else ordered_state()
    if condition == "wrong-order":
        state["events.json"] = list(reversed(state["events.json"]))
    if condition == "injected":
        state.pop("events.json")
    root = make_snapshot(tmp_path, state)
    evidence.validate_snapshot(root, **IDENTITY)
    checks, _, _ = flow_module().build_checks(root, evidence.load_json)
    assert float(all(c["passed"] for c in checks)) == expected


def test_identity_and_corruption_are_infrastructure_errors(tmp_path):
    root = make_snapshot(tmp_path, ordered_state())
    with pytest.raises(ValueError, match="trial_id mismatch"):
        evidence.validate_snapshot(root, **{**IDENTITY, "trial_id": "different"})
    (root / "Documents/events.json").write_text("[]")
    with pytest.raises(ValueError, match="checksum"):
        evidence.validate_snapshot(root, **IDENTITY)


def test_corrupt_file_does_not_become_empty_state(tmp_path):
    container = tmp_path / "app"
    (container / "Documents").mkdir(parents=True)
    (container / "Documents/events.json").write_text("{")
    with pytest.raises(ValueError):
        evidence.snapshot(container, tmp_path / "out", **IDENTITY, device="udid", backend="local")
    assert not (tmp_path / "out/manifest.json").exists()


def test_replay_needs_no_mac_and_rejects_wrong_trial(tmp_path):
    root = make_snapshot(tmp_path, ordered_state())
    script = REPO / "tasks/simbench" / FLOW_TASK / "tests/verify.py"
    result = subprocess.run([sys.executable, str(script), str(tmp_path / "reward.json"),
                             "--evidence", str(root), "--trial-id", "wrong"], capture_output=True)
    assert result.returncode == 2
    assert json.loads((tmp_path / "reward.json").read_text()) == {"reward": 0.0, "sim_runner_ok": 0.0}
    result = subprocess.run([sys.executable, str(script), str(tmp_path / "reward.json"),
                             "--evidence", str(root), "--trial-id", "test-trial"], capture_output=True)
    assert result.returncode == 0
    assert json.loads((tmp_path / "reward.json").read_text())["reward"] == 1


def test_device_selection_never_chooses_arbitrary_booted_device(monkeypatch):
    monkeypatch.setattr(evidence, "simctl", lambda *args: json.dumps({"devices": {
        "ios-a": [{"udid": "one", "name": "iPhone 17"}],
        "ios-b": [{"udid": "two", "name": "iPhone 17"}],
    }}))
    with pytest.raises(ValueError, match="matched 2"):
        evidence.resolve_device("iPhone 17")
    assert evidence.resolve_device("two") == "two"


def test_helpers_and_checks_stay_vendored_in_sync():
    source = (REPO / "src/expo_harbor_evals/simbench_evidence.py").read_text()
    for path in (REPO / "tasks/simbench").glob("*/tests/simbench_evidence.py"):
        assert path.read_text() == source


def test_calibration_rejects_missing_attempts_and_failed_oracle(tmp_path):
    assert not check_calibration(tmp_path, 1, True)["ok"]
    raw = {"agent_info": {"name": "oracle"}, "verifier_result": {
        "rewards": {"reward": 1.0, "sim_runner_ok": 1.0}}}
    evidence.write_json(tmp_path / "oracle/result.json", raw)
    evidence.write_json(tmp_path / "nop/result.json", {
        "agent_info": {"name": "nop"}, "verifier_result": {
            "rewards": {"reward": 0.0, "sim_runner_ok": 1.0}}})
    assert check_calibration(tmp_path, 1, False)["ok"]
    (tmp_path / "oracle/agent").mkdir()
    (tmp_path / "oracle/agent/exit-code.txt").write_text("1")
    assert not check_calibration(tmp_path, 1, False)["ok"]


def test_report_separates_backends_and_reports_invalid_trials(tmp_path):
    for backend in ("local-macos", "eas-macos"):
        evidence.write_json(tmp_path / backend / "result.json", {
            "agent_info": {"name": "nop"}, "verifier_result": {
                "rewards": {"reward": 0.0, "sim_runner_ok": 1.0}}})
        evidence.write_json(tmp_path / backend / "verifier/details.json", {"manifest": {"backend": backend}})
    evidence.write_json(tmp_path / "broken/result.json", {
        "verifier_result": {"rewards": {"reward": 0.0, "sim_runner_ok": 0.0}}})
    _, trials = load_runs([tmp_path])
    broken = next(t for t in trials if t.name == "broken")
    assert broken.reward is None and "Infrastructure failure" in broken.error
    assert len(build_series(trials)) == 3


@pytest.mark.parametrize("record_path", ["artifacts/device.json", "artifacts/logs/artifacts/device.json",
                                         "_local_env/logs/artifacts/device.json"])
def test_recovery_only_deletes_matching_trial_devices(tmp_path, monkeypatch, record_path):
    import expo_harbor_evals.simbench_calibrate as calibration
    evidence.write_json(tmp_path / "trial" / record_path, {
        "device": "owned", "session": "harbor-123456abcdef"})
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps({"devices": {"ios": [
            {"udid": "owned", "name": "harbor-123456abcdef"},
            {"udid": "other", "name": "User simulator"},
        ]}}))
    monkeypatch.setattr(calibration.subprocess, "run", run)
    assert cleanup_devices(tmp_path) == []
    assert [c for c in calls if "delete" in c] == [["xcrun", "simctl", "delete", "owned"]]
    evidence.write_json(tmp_path / "trial" / record_path, {
        "device": "other", "session": "harbor-123456abcdef"})
    calls.clear()
    assert cleanup_devices(tmp_path)
    assert not any("delete" in c for c in calls)


def test_calibration_reports_truncated_result(tmp_path):
    (tmp_path / "trial").mkdir()
    (tmp_path / "trial/result.json").write_text('{"agent_info":')
    result = check_calibration(tmp_path, 1, False)
    assert not result["ok"]
    assert "Invalid trial result" in result["trials"][0]["error"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
@pytest.mark.parametrize("shell_wait", ["wait", "exit 0"])
def test_local_timeout_stops_child_processes(tmp_path, shell_wait):
    env = SimpleNamespace(_root=tmp_path, _wrap_command=lambda c: c, _map_command=lambda c: c,
                          _map_path=lambda p: tmp_path / p.lstrip("/"), _default_cwd=lambda: tmp_path,
                          _merge_env=lambda e: e, _output_callback=lambda: None)
    command = f"sleep 60 & echo $! > {shlex.quote(str(tmp_path / 'child.pid'))}; {shell_wait}"
    with pytest.raises(TimeoutError):
        asyncio.run(LocalHostEnvironment.exec(env, command, timeout_sec=1))
    pid = (tmp_path / "child.pid").read_text().strip()
    state = subprocess.run(["ps", "-p", pid, "-o", "state="], capture_output=True, text=True).stdout.strip()
    assert not state or state.startswith("Z"), f"Child survived timeout: {pid} ({state})"
