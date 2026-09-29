from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from expo_harbor_evals.codegen_calibrate import assess_bracket
from expo_harbor_evals.evaluation_identity import make_suite, trial_identity
from expo_harbor_evals.mobile_eval import CandidateFailure, execute, prepare
from expo_harbor_evals.mobile_scenarios import slider_fraction
from expo_harbor_evals.report import build_series, load_runs, group_tasks, series_stats
from expo_harbor_evals.simbench_evidence import write_json

REPO = Path(__file__).resolve().parents[1]
PICKER = "sdk-04-image-picker-canceled-assets-guard"
MODAL = "feedback-04-modal-editor-touch-freeze"


def judged(task, failed):
    rubric = tomllib.loads((task / "tests/requirements/rubric.toml").read_text())
    rows = [{"id": c["id"], "value": float(c["id"] not in failed)} for c in rubric["criterion"]]
    return {"reward": round(sum(r["value"] for r in rows) / len(rows), 4), "guarded": False, "criteria": rows}


def test_wrong_success_path_must_fail_its_actual_criterion():
    task = REPO / "tasks/codegen" / PICKER
    assert assess_bracket(task, "distractor", judged(task, {"successful-selection-updates-preview"}))[0]
    # An unrelated low grade does not calibrate the missing-preview bug.
    assert not assess_bracket(task, "distractor", judged(task, {"uses-current-canceled-spelling"}))[0]


def test_calibration_rejects_missing_duplicate_and_inconsistent_details():
    task = REPO / "tasks/codegen" / PICKER
    result = judged(task, set())
    assert assess_bracket(task, "reference", result)[0]
    result["criteria"] = result["criteria"][:-1]
    assert not assess_bracket(task, "reference", result)[0]
    result = judged(task, set())
    result["criteria"].append(result["criteria"][0])
    assert not assess_bracket(task, "reference", result)[0]
    result = judged(task, {"assets-null-guard"})
    result["reward"] = 1
    assert not assess_bracket(task, "reference", result)[0]


@pytest.mark.parametrize("bracket", ["baseline-comment", "distractor"])
def test_calibration_rejects_judge_timeouts_on_negative_controls(bracket):
    task = REPO / "tasks/codegen" / PICKER
    rubric = tomllib.loads((task / "tests/requirements/rubric.toml").read_text())
    result = judged(task, {c["id"] for c in rubric["criterion"]})
    assert assess_bracket(task, bracket, result)[0]  # A legitimate zero is valid.
    for row in result["criteria"]:
        row["error"] = "judge timed out after 300s"
    assert not assess_bracket(task, bracket, result)[0]


def test_all_negative_controls_name_real_failures():
    for task in (REPO / "tasks/codegen").iterdir():
        if not (task / "task.toml").exists():
            continue
        spec = json.loads((task / "tests/requirements/calibration.json").read_text())
        ids = {c["id"] for c in tomllib.loads((task / "tests/requirements/rubric.toml").read_text())["criterion"]}
        assert spec["baseline-comment"]["must_fail"]
        for name in ("baseline-comment", "distractor"):
            if name in spec:
                assert set(spec[name]["must_fail"]) <= ids
        assert ("distractor" in spec) == (task / "solution/distractor").is_dir()


def test_native_prepare_uses_candidate_and_keeps_secrets_out(tmp_path):
    candidate = tmp_path / "candidate"
    shutil.copytree(REPO / "tasks/codegen" / MODAL / "environment", candidate)
    (candidate / "FeedScreen.tsx").write_text("export default function ChangedCandidate() { return null }\n")
    (candidate / ".env.local").write_text("EXPO_TOKEN=do-not-copy\n")
    out = tmp_path / "prepared"
    spec = prepare(MODAL, candidate, out)
    assert "ChangedCandidate" in (out / "app/submitted/FeedScreen.tsx").read_text()
    assert not (out / "app/submitted/.env.local").exists()
    assert "do-not-copy" not in (out / "input.json").read_text()
    assert (out / "app/package-lock.json").exists()
    assert spec["validation_status"] == "requires-native-calibration"


def test_native_prepare_rejects_changed_stack_and_output_inside_input(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "App.tsx").write_text("export default () => null")
    write_json(candidate / "package.json", {"dependencies": {"react-native": "different"}})
    with pytest.raises(CandidateFailure, match="Dependency"):
        prepare(MODAL, candidate, tmp_path / "out")
    with pytest.raises(ValueError, match="outside"):
        prepare(MODAL, candidate, candidate / "out")


def test_native_tampering_rejected_before_any_commands(tmp_path):
    candidate = REPO / "tasks/codegen" / MODAL / "environment"
    out = tmp_path / "prepared"
    prepare(MODAL, candidate, out)
    (out / "app/submitted/FeedScreen.tsx").write_text("export default () => null")
    with pytest.raises(ValueError, match="source changed"):
        execute(out)


def test_native_missing_tool_is_infrastructure_not_candidate_failure(tmp_path, monkeypatch):
    out = tmp_path / "prepared"
    prepare(MODAL, REPO / "tasks/codegen" / MODAL / "environment", out)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = execute(out)
    assert result["status"] == "infra-error"
    assert json.loads((out / "reward.json").read_text()) == {"reward": 0, "mobile_runner_ok": 0}


def test_native_slider_evidence_cannot_default_to_passing_midpoint():
    assert slider_fraction({"value": "50%"}) == 0.5
    assert slider_fraction({"value": "0%"}) == 0
    with pytest.raises(RuntimeError):
        slider_fraction({"label": "50%"})


def test_native_calibration_requires_built_app_and_all_reference_checks():
    from expo_harbor_evals.mobile_calibrate import assess_control
    from expo_harbor_evals.mobile_scenarios import EXPECTED_CHECKS
    reference = {"status": "passed", "input": {"profile": "picker"}, "errors": [],
        "checks": [{"name": name, "passed": True} for name in ["candidate-build", *EXPECTED_CHECKS["picker"]]]}
    assert assess_control("reference-alternative", reference)
    reference["checks"].pop()
    with pytest.raises(ValueError, match="complete"):
        assess_control("reference", reference)
    broken = {"status": "failed", "errors": [], "checks": [
        {"name": "candidate-build", "passed": True}, {"name": "native-ui", "passed": False}]}
    assert assess_control("baseline", broken)
    broken["checks"][0]["passed"] = False
    assert not assess_control("baseline", broken)
    broken["status"] = "infra-error"
    assert not assess_control("baseline", broken)


def test_invalid_native_submission_is_a_scored_failure(tmp_path, monkeypatch):
    from expo_harbor_evals import mobile_eval
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["expo-mobile-eval", "run", "--task", MODAL,
                        "--candidate", str(candidate), "--output", str(output)])
    with pytest.raises(SystemExit) as exc:
        mobile_eval.main()
    assert exc.value.code == 1
    assert json.loads((output / "reward.json").read_text()) == {"reward": 0, "mobile_runner_ok": 1}
    assert not (output / "app").exists()


def test_native_build_failure_is_distinct_from_missing_tool(tmp_path, monkeypatch):
    import subprocess
    from expo_harbor_evals import mobile_eval
    output = tmp_path / "out"
    prepare(MODAL, REPO / "tasks/codegen" / MODAL / "environment", output)
    commands = []
    def fake_run(self, args, **kwargs):
        commands.append(args)
        if args == ["agent-device", "--version"]:
            return "0.19.3"
        if args[:2] == ["pod", "install"]:
            (output / "app/ios/HarborCandidate.xcworkspace").mkdir(parents=True)
            (output / "app/ios/Podfile.lock").write_text("test fixture")
        if "runtimes" in args:
            return json.dumps({"runtimes": [{"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                "version": "26.5", "isAvailable": True}]})
        if "create" in args:
            return "owned-device"
        if args[0] == "xcodebuild" and "build" in args:
            raise subprocess.CalledProcessError(65, args, output="test-build.log")
        return "test-version"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shutil, "which", lambda name: f"/test/{name}")
    monkeypatch.delenv("SIMBENCH_RUNTIME", raising=False)
    monkeypatch.setattr(mobile_eval.Commands, "run", fake_run)
    result = execute(output)
    assert result["status"] == "failed" and result["checks"][0]["name"] == "candidate-build"
    assert ["xcrun", "simctl", "delete", "owned-device"] in commands
    assert json.loads((output / "reward.json").read_text())["mobile_runner_ok"] == 1


def test_suite_and_report_separate_changed_experiments(tmp_path):
    task = tmp_path / "tasks/codegen/example"
    task.mkdir(parents=True)
    (task / "task.toml").write_text('[metadata]\nfamily="expo-codegen"\n')
    (task / "instruction.md").write_text("One task")
    write_json(tmp_path / "suites/mobile-v2.json", make_suite(tmp_path))
    identities = [trial_identity(task, {"agent": {"kwargs": {"preface": text}}}) for text in ("first", "second")]
    assert identities[0]["experiment_sha256"] != identities[1]["experiment_sha256"]
    cohort = trial_identity(task, {}, {"datasets": [{"path": "tasks/codegen", "task_names": ["example"]}]})
    assert cohort["experiment_sha256"] != trial_identity(task, {})["experiment_sha256"]
    for i, identity in enumerate(identities):
        write_json(tmp_path / f"runs/trial{i}/evaluation.json", identity)
        write_json(tmp_path / f"runs/trial{i}/result.json", {"task_name": "example",
            "agent_info": {"name": "test", "model_info": {"name": "model"}},
            "verifier_result": {"rewards": {"reward": 1}}})
    _, trials = load_runs([tmp_path / "runs"])
    assert len(build_series(trials)) == 2
    (task / "instruction.md").write_text("Different task")
    with pytest.raises(ValueError, match="Task changed"):
        trial_identity(task, {})


@pytest.mark.parametrize("kind,measurement", [("file-exists", "programmatic-checks"), ("ai-review", "source-and-checks")])
def test_rewardkit_recipes_have_distinct_measurement_identity(tmp_path, kind, measurement):
    task = tmp_path / "tasks/codegen/example"
    task.mkdir(parents=True)
    (task / "task.toml").write_text('[metadata]\nfamily="expo-codegen"\n')
    write_json(task / "tests/requirements/grading.json", {"checks": {"first": {"kind": "file-exists"}, "second": {"kind": kind}}})
    write_json(tmp_path / "suites/mobile-v2.json", make_suite(tmp_path))
    assert trial_identity(task, {})["measurement"] == measurement
    assert trial_identity(task, {"verifier": {"env": {"EXPO_EVAL_VERIFIER_MODE": "reference"}}})["measurement"] == "reference-smoke"


def test_report_completion_includes_infrastructure_errors(tmp_path):
    for name, rewards in (("pass", {"reward": 1, "sim_runner_ok": 1}),
                          ("error", {"reward": 0, "sim_runner_ok": 0})):
        write_json(tmp_path / name / "result.json", {"task_name": "same",
            "agent_info": {"name": "test"}, "verifier_result": {"rewards": rewards}})
    _, trials = load_runs([tmp_path])
    stat = series_stats(group_tasks(trials), trials[0].series_key)
    assert stat.mean == 1  # conditional on valid results, explicitly separate
    assert stat.completion_rate == 0.5 and stat.errors == 1 and stat.attempts == 2
    assert stat.solved == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS seatbelt")
@pytest.mark.parametrize("task_location", ["tasks/example", "outputs/studio/draft/example"])
def test_candidate_can_read_app_but_not_reference_files(tmp_path, task_location):
    from expo_harbor_evals.mac_sandbox_env import MacSandboxEnvironment, PROFILE_TEMPLATE
    env = object.__new__(MacSandboxEnvironment)
    env._root = tmp_path / "runs/trial/_local_env"
    env.environment_dir = tmp_path / task_location / "environment"
    env.environment_dir.mkdir(parents=True)
    reference = env.environment_dir.parent / "reference.txt"
    reference.write_text("hidden answer")
    write_json(tmp_path / "suites/mobile-v2.json", {})
    other_answers = [tmp_path / name for name in (
        "tasks/other/reference.txt",
        ".studio/drafts/copy.json",
        "outputs/studio/other-copy/reference.txt",
    )]
    for answer in other_answers:
        answer.parent.mkdir(parents=True, exist_ok=True)
        answer.write_text("hidden answer")
    (env._root / "app").mkdir(parents=True)
    (env._root / "app/input.txt").write_text("visible input")
    env._profile_path = env._root / "sandbox.sb"
    env._profile_path.write_text(PROFILE_TEMPLATE.format(root=env._root, home=Path.home()))
    env._default_cwd = lambda: env._root / "app"
    env._merge_env = lambda value: value
    env._output_callback = lambda: None
    result = asyncio.run(env.exec_agent(command="cat /app/input.txt"))
    assert result.return_code == 0 and result.stdout.strip() == "visible input"
    import shlex
    for answer in (reference, *other_answers):
        result = asyncio.run(env.exec(command=f"cat {shlex.quote(str(answer))}"))
        assert result.return_code == 0 and result.stdout.strip() == "hidden answer"
        result = asyncio.run(env.exec_agent(command=f"cat {shlex.quote(str(answer))}"))
        assert result.return_code != 0 and "hidden answer" not in (result.stdout or "")


def test_draft_calibration_is_explicitly_unversioned_and_cannot_bypass_locked_tasks(tmp_path):
    task = tmp_path / 'tasks/simbench/locked'
    task.mkdir(parents=True)
    (task / 'task.toml').write_text('[metadata]\nfamily="simbench"\n')
    write_json(tmp_path / 'suites/mobile-v2.json', make_suite(tmp_path))
    draft = tmp_path / 'outputs/studio/new-simulator-task'
    shutil.copytree(task, draft)
    with pytest.raises(ValueError, match='Task changed'):
        trial_identity(draft, {})
    identity = trial_identity(draft, {}, allow_unversioned=True)
    assert identity['measurement'] == 'unversioned'
    (draft / 'instruction.md').write_text('Changed draft')
    assert trial_identity(draft, {}, allow_unversioned=True)['experiment_sha256'] != identity['experiment_sha256']
    (task / 'instruction.md').write_text('Changed locked task')
    with pytest.raises(ValueError, match='Task changed'):
        trial_identity(task, {}, allow_unversioned=True)
    new_library_task = tmp_path / 'tasks/simbench/unlocked'
    shutil.copytree(draft, new_library_task)
    with pytest.raises(ValueError, match='Task changed'):
        trial_identity(new_library_task, {}, allow_unversioned=True)
