"""Reporting checks use fabricated records; no apps, simulators or judges run."""

import json
from pathlib import Path

from expo_harbor_evals.evaluation_identity import make_suite
from expo_harbor_evals.report import Trial, build_html, build_series, group_tasks, load_runs, series_stats
from expo_harbor_evals.report_view import coverage, evidence_files, render_matrix
from expo_harbor_evals.simbench_evidence import write_json


def trial(**changes):
    values = dict(name="example", task="modal", agent="example", model="A", reward=1,
        criteria=[], judge={}, error=None, cost_usd=None, input_tokens=None,
        cache_tokens=None, output_tokens=None, measurement="native-ui")
    return Trial(**{**values, **changes})


def test_modes_separate_even_without_an_experiment_hash():
    records = [trial(), trial(measurement="source-review")]
    assert len(build_series(records)) == 2
    page = build_html(records, "Example", "fixtures", illustrative=True)
    assert 'id="lane-native-ui"' in page and 'id="lane-source-review"' in page
    assert "fabricated records" in page
    assert "no combined mobile-app score" in page


def test_policy_modes_and_regrades_keep_scope_and_spend_separate(tmp_path):
    write_json(tmp_path / "regraded/result.json", {"task_name": "paywall",
        "agent_info": {"name": "claude-host", "model_info": {"name": "sonnet"}},
        "config": {"source_trial": {"action": "regrade", "path": "runs/original"}},
        "agent_result": {"cost_usd": 2, "n_output_tokens": 1000, "metadata": {"num_turns": 5}},
        "verifier_result": {"rewards": {"reward": 0}}})
    write_json(tmp_path / "regraded/evaluation.json", {"measurement": "source-and-policy"})
    _, records = load_runs([tmp_path])
    assert records[0].cost_usd == 0 and records[0].output_tokens == 0 and records[0].steps == 0
    assert records[0].regrade_of == "runs/original"
    assert records[0].series_key.endswith("|regrade")
    page = build_html([*records, trial(measurement="policy-behavior")], "Regrades", "fixtures")
    assert 'id="lane-source-and-policy"' in page and 'id="lane-policy-behavior"' in page
    assert "No new generation" in page and "saved submissions regraded" in page
    from expo_harbor_evals.viewer import render_trial
    live_page = render_trial(tmp_path.parent, tmp_path.name, "regraded")
    assert "Regraded from" in live_page and "No new generation" in live_page
    assert '<td>Agent cost</td><td>$0.00</td>' in live_page
    assert '<td>Agent steps</td><td>0</td>' in live_page


def test_pending_is_not_an_execution_error_or_completed_attempt():
    records = [trial(), trial(name="waiting", reward=None, pending=True)]
    stat = series_stats(group_tasks(records), records[0].series_key)
    assert stat.attempts == 1 and stat.errors == 0 and stat.completion_rate == 1
    assert stat.solved == 0
    assert records[1].outcome == "pending"


def test_missing_planned_attempts_do_not_render_as_a_complete_green_cell():
    records = [trial(name=str(i), run="one-run", planned_tasks=("modal", "picker"), planned_attempts=3) for i in range(2)]
    assert coverage(records) == ({"modal", "picker"}, 6)
    matrix = render_matrix(records)
    assert "1 missing result" in matrix and "3 missing results" in matrix
    assert 'class="result-cell pass"' not in matrix
    assert coverage([trial()])[1] is None


def test_harbor_native_checks_and_pending_plan_load(tmp_path):
    write_json(tmp_path / "config.json", {"agents": [{"name": "example"}],
        "datasets": [{"path": "tasks/codegen", "task_names": ["modal", "picker"]}]})
    write_json(tmp_path / "done/result.json", {"task_name": "modal", "agent_info": {"name": "example"},
        "verifier_result": {"rewards": {"reward": 0, "mobile_runner_ok": 1}}})
    write_json(tmp_path / "done/verifier/details.json", {"backend": "eas-macos", "checks": [
        {"name": "save-and-return", "passed": False, "notes": "Feed stayed stale"}]})
    write_json(tmp_path / "waiting/config.json", {"task": {"path": "tasks/codegen/picker"}, "agent": {"name": "example"}})
    _, records = load_runs([tmp_path])
    done = next(t for t in records if t.name == "done")
    assert done.checks[0]["notes"] == "Feed stayed stale" and done.backend == "eas-macos"
    assert done.planned_attempts == 1  # Harbor's serialized default
    assert next(t for t in records if t.name == "waiting").pending
    write_json(tmp_path / "result.json", {"finished_at": "2026-09-10T10:00:00Z"})
    _, records = load_runs([tmp_path])
    waiting = next(t for t in records if t.name == "waiting")
    assert waiting.outcome == "error" and "no result" in waiting.error
    write_json(tmp_path / "config.json", {"agents": [{"name": "example"}],
        "datasets": [{"task_names": ["modal*"], "n_tasks": 1}]})
    _, records = load_runs([tmp_path])
    assert coverage(records)[1] is None


def test_standalone_native_evidence_is_read_without_inventing_an_agent(tmp_path):
    output = tmp_path / "evidence/native-eval"
    write_json(output / "details.json", {"kind": "native-ui", "task": "picker", "status": "failed",
        "backend": "eas-macos", "checks": [{"name": "candidate-build", "passed": False}],
        "input": {"profile": "picker", "submission": {"App.tsx": "test"}}, "errors": []})
    _, records = load_runs([tmp_path, output])
    assert len(records) == 1
    assert records[0].agent == "submitted-app" and records[0].reward == 0
    assert records[0].cost_usd is None and records[0].checks
    data = json.loads((output / "details.json").read_text())
    data["status"] = "passed"  # Claimed pass, but missing scenario checks.
    write_json(output / "details.json", data)
    _, records = load_runs([tmp_path])
    assert records[0].outcome == "error" and records[0].reward is None


def test_historical_judge_timeout_is_an_error_not_a_candidate_failure(tmp_path):
    write_json(tmp_path / "trial/result.json", {"task_name": "picker", "agent_info": {"name": "example"},
        "verifier_result": {"rewards": {"reward": 0}}})
    write_json(tmp_path / "trial/verifier/reward-details.json", {"reward": {"criteria": [
        {"id": "preview", "value": 0, "error": "judge timed out after 300s"}]}})
    _, records = load_runs([tmp_path])
    assert records[0].outcome == "error" and records[0].reward is None
    stats = series_stats(group_tasks(records), records[0].series_key)
    assert stats.errors == 1 and stats.mean is None


def test_native_calibration_control_names_and_application_outcomes(tmp_path):
    write_json(tmp_path / "calibration.json", {"kind": "native-scenario-calibration"})
    write_json(tmp_path / "baseline-1/evaluation/details.json", {"kind": "native-ui",
        "task": "picker", "status": "failed", "checks": [{"name": "candidate-build", "passed": True},
        {"name": "native-ui", "passed": False}], "errors": []})
    _, records = load_runs([tmp_path])
    assert len(records) == 1 and records[0].agent == "calibration-control"
    assert records[0].name == "baseline-1" and records[0].model == "Control: baseline"
    assert records[0].outcome == "fail"
    page = build_html(records, "Calibration", "fixtures")
    assert "application outcomes" in page and "calibration.json" in page


def test_report_escapes_names_reasons_and_native_errors():
    payload = '</script><script>alert("untrusted")</script>'
    page = build_html([trial(task=payload, error=payload, checks=[{"name": payload,
        "passed": False, "notes": payload}])], payload, payload)
    assert payload not in page
    assert "&lt;/script&gt;" in page


def test_report_embeds_owned_evidence_and_ignores_symlinked_files(tmp_path):
    owned = tmp_path / "trial"
    owned.mkdir()
    external = tmp_path / "external.png"
    external.write_bytes(b"outside")
    (owned / "failure.png").symlink_to(external)
    assert evidence_files(trial(source_dir=owned))[0] == []
    (owned / "failure.png").unlink()
    fixture = Path(__file__).resolve().parents[1] / "mobile/templates/sdk56/fixture.png"
    (owned / "failure.png").write_bytes(fixture.read_bytes())
    page = build_html([trial(source_dir=owned, reward=0)], "Example", "fixtures")
    assert "data:image/png;base64," in page
    assert "failure.png" in page


def test_presentation_changes_do_not_invalidate_the_evaluation_suite(tmp_path):
    code = tmp_path / "src/expo_harbor_evals"
    code.mkdir(parents=True)
    (code / "report.py").write_text("before")
    (code / "mobile_scenarios.py").write_text("score logic")
    before = make_suite(tmp_path)
    (code / "report.py").write_text("after")
    (code / "report_view.py").write_text("new layout")
    assert make_suite(tmp_path) == before
    (code / "mobile_scenarios.py").write_text("different score logic")
    assert make_suite(tmp_path) != before
