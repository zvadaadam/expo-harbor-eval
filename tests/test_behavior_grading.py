import json
import shutil
import sys
from pathlib import Path

import pytest

from expo_harbor_evals.codegen_rewardkit_runner import (
    apply_behavior, main, prepare_rubric, reject_judge_errors, run_behavior,
)

TASK = Path(__file__).resolve().parents[1] / "tasks/codegen/feedback-11-anonymous-paywall-eligibility"
RUBRIC = TASK / "tests/requirements"


@pytest.mark.parametrize("control,expected", [
    ("environment", 0), ("solution/reference", 1),
    ("solution/reference-alternative", 1), ("solution/distractor", 0),
])
def test_behavior_runs_real_policy_controls(tmp_path, control, expected):
    result = run_behavior(RUBRIC, TASK / control, tmp_path / "reward.json")
    assert result["score"] == expected
    assert result["evidence"]["checks"] == 4860


def test_behavior_rejects_source_judge_false_positive(tmp_path):
    behavior = run_behavior(RUBRIC, TASK / "environment", tmp_path / "reward.json")
    rows = [{**row, "value": 1.0} for row in behavior["criteria"]]
    rows.append({"id": "state-driven-screen-preserved", "value": 1.0})
    (tmp_path / "reward-details.json").write_text(json.dumps({"reward": {"score": 1, "criteria": rows}}))
    scores = apply_behavior(tmp_path / "reward.json", behavior)
    assert scores == {"reward": 0, "source_review": 1, "policy_behavior": 0}
    details = json.loads((tmp_path / "reward-details.json").read_text())
    failed = {row["id"] for row in details["reward"]["criteria"] if not row["value"]}
    assert failed == {"anonymous-and-identified-eligibility"}


def test_policy_pass_does_not_excuse_disconnected_screen(tmp_path):
    behavior = run_behavior(RUBRIC, TASK / "solution/reference", tmp_path / "reward.json")
    rows = [*behavior["criteria"], {"id": "state-driven-screen-preserved", "value": 0.0}]
    (tmp_path / "reward-details.json").write_text(json.dumps({"reward": {"score": .75, "criteria": rows}}))
    assert apply_behavior(tmp_path / "reward.json", behavior)["reward"] == 0


@pytest.mark.parametrize("screen_rows", [[],
    [{"id": "state-driven-screen-preserved", "value": .5}],
    [{"id": "state-driven-screen-preserved", "value": 1}] * 2,
])
def test_incomplete_or_malformed_source_review_cannot_pass(tmp_path, screen_rows):
    behavior = run_behavior(RUBRIC, TASK / "solution/reference", tmp_path / "reward.json")
    (tmp_path / "reward-details.json").write_text(json.dumps({"reward": {
        "score": 1, "criteria": [*behavior["criteria"], *screen_rows]}}))
    with pytest.raises(ValueError, match="every required binary criterion"):
        apply_behavior(tmp_path / "reward.json", behavior)


def test_failed_policy_skips_paid_source_judge_in_normal_mode(tmp_path, monkeypatch):
    import rewardkit.runner

    app = tmp_path / "app"
    shutil.copytree(TASK / "environment", app)
    # Bypass the unchanged-source guard without repairing the policy.
    with (app / "paywall.js").open("a") as stream:
        stream.write("\n// A plausible submission that is still wrong.\n")
    output = tmp_path / "reward.json"
    monkeypatch.setattr(sys, "argv", ["run_rewardkit", str(RUBRIC), str(app), str(output)])
    def unexpected_judge(*args, **kwargs):
        pytest.fail("A failed required policy must not invoke a paid judge")
    monkeypatch.setattr(rewardkit.runner, "run", unexpected_judge)
    main()
    assert json.loads(output.read_text()) == {"reward": 0, "policy_behavior": 0}
    detail = json.loads((tmp_path / "reward-details.json").read_text())["reward"]
    assert detail["source_review_skipped"]
    assert detail["measurement"] == "source-and-policy"
    from expo_harbor_evals.codegen_calibrate import assess_bracket
    result = {"reward": 0, "guarded": False, **detail}
    assert assess_bracket(TASK, "baseline-comment", result)[0]
    result["criteria"] = [{**row, "value": 1} for row in detail["criteria"]]
    assert not assess_bracket(TASK, "reference", result)[0]


@pytest.mark.parametrize("source", [
    "module.exports.getPaywallOffering = () => { while (true) {} };",
    "Object.defineProperty(module.exports, 'getPaywallOffering', { get() { while (true) {} } });",
    "module.exports.getPaywallOffering = () => process.env.ANTHROPIC_API_KEY;",
    "require('node:assert/strict').equal = () => {};",
    "module.exports.getPaywallOffering = () => globalThis.constructor.constructor('return process')();",
    "this is not javascript",
])
def test_invalid_or_host_accessing_helpers_fail_without_hanging(tmp_path, source):
    app = tmp_path / "app"
    app.mkdir()
    (app / "paywall.js").write_text(source)
    behavior = run_behavior(RUBRIC, app, tmp_path / "reward.json")
    assert behavior["score"] == 0


def test_missing_node_is_an_execution_error(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Node.js"):
        run_behavior(RUBRIC, TASK / "environment", tmp_path / "reward.json")
    assert not (tmp_path / "reward.json").exists()


def test_upstream_schema_rejects_misspelled_criterion_before_judging(tmp_path):
    rubric = tmp_path / "rubric"
    shutil.copytree(RUBRIC, rubric)
    path = rubric / "rubric.toml"
    path.write_text(path.read_text().replace('type = "binary"', 'type = "bniary"', 1))
    with pytest.raises(ValueError, match="bniary"):
        prepare_rubric(rubric, tmp_path / "prepared", TASK / "environment", None, None)


def test_nested_judge_errors_never_publish_a_score(tmp_path):
    output = tmp_path / "reward.json"
    output.write_text('{"reward": 1}')
    (tmp_path / "reward-details.json").write_text(json.dumps({"reward": {
        "kind": "group", "components": [{"detail": {"criteria": [{"error": "timeout"}]}}]
    }}))
    with pytest.raises(RuntimeError, match="timeout"):
        reject_judge_errors(output)
    assert not output.exists()
