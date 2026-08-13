"""Token usage and cost must survive from trial result.json into the exports.

The claude CLI envelope's usage lands in each trial's agent_result
(n_input_tokens / n_cache_tokens / n_output_tokens / cost_usd). These tests
pin the read-side field names and the aggregation so a rename in either
layer breaks loudly instead of silently dropping spend from the report and
results/history.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path

from expo_harbor_evals.export import summarize_run
from expo_harbor_evals.report import (
    fmt_tokens,
    group_tasks,
    load_runs,
    series_stats,
)


def _write_trial(
    run_dir: Path,
    name: str,
    task: str,
    reward: float | None,
    agent_result: dict | None,
    error: str | None = None,
) -> None:
    trial_dir = run_dir / name
    trial_dir.mkdir(parents=True)
    result: dict = {
        "task_name": f"tasks/simbench/{task}",
        "trial_name": name,
        "agent_info": {
            "name": "claude-host",
            "model_info": {"name": "sonnet#agent-device"},
        },
    }
    if agent_result is not None:
        result["agent_result"] = agent_result
    if reward is not None:
        result["verifier_result"] = {"rewards": {"reward": reward}}
    if error is not None:
        result["exception_info"] = {"exception_message": error}
    (trial_dir / "result.json").write_text(json.dumps(result))


def _write_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "usage-run"
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps({"finished_at": "2026-08-12T00:00:00+00:00"})
    )
    _write_trial(
        run_dir,
        "task-a__1",
        "simbench-ios-01-task-a",
        reward=1.0,
        agent_result={
            "n_input_tokens": 700,
            "n_cache_tokens": 5_000_000,
            "n_output_tokens": 19_000,
            "cost_usd": 0.75,
        },
    )
    _write_trial(
        run_dir,
        "task-b__1",
        "simbench-ios-02-task-b",
        reward=0.5,
        agent_result={
            "n_input_tokens": 300,
            "n_cache_tokens": 1_000_000,
            "n_output_tokens": 1_000,
            "cost_usd": 0.25,
        },
    )
    # Errored before the CLI produced an envelope: no usage at all. Must not
    # break the sums and must not count as solved.
    _write_trial(
        run_dir,
        "task-c__1",
        "simbench-ios-03-task-c",
        reward=None,
        agent_result=None,
        error="agent crashed",
    )
    return run_dir


def test_series_stats_sums_cost_and_tokens(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    _, trials = load_runs([run_dir])
    tasks = group_tasks(trials)
    (key,) = {t.series_key for t in trials}

    stat = series_stats(tasks, key)
    assert stat.total_cost == 1.0
    assert stat.mean_cost == 0.5
    assert stat.input_tokens == 1_000
    assert stat.cache_tokens == 6_000_000
    assert stat.output_tokens == 20_000
    assert stat.solved == 1 and stat.n_tasks == 3


def test_history_export_keeps_usage(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    summary = summarize_run(run_dir)
    assert summary is not None

    assert summary["total_cost_usd"] == 1.0
    (row,) = summary["series"]
    assert row["total_cost_usd"] == 1.0
    assert row["mean_cost_usd"] == 0.5
    assert row["n_input_tokens"] == 1_000
    assert row["n_cache_tokens"] == 6_000_000
    assert row["n_output_tokens"] == 20_000


def test_usage_absent_stays_none_not_zero(tmp_path: Path) -> None:
    """A run with no recorded usage must export null, not a fake $0."""
    run_dir = tmp_path / "runs" / "no-usage"
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps({"finished_at": "2026-08-12T00:00:00+00:00"})
    )
    _write_trial(
        run_dir, "task-a__1", "simbench-ios-01-task-a", reward=0.0, agent_result=None
    )
    summary = summarize_run(run_dir)
    assert summary is not None
    assert summary["total_cost_usd"] is None
    (row,) = summary["series"]
    assert row["total_cost_usd"] is None
    assert row["n_output_tokens"] is None


def test_fmt_tokens() -> None:
    assert fmt_tokens(None) == "—"
    assert fmt_tokens(777) == "777"
    assert fmt_tokens(1_234) == "1.2k"
    assert fmt_tokens(19_510) == "20k"
    assert fmt_tokens(5_359_260) == "5.4M"
    assert fmt_tokens(123_000_000) == "123M"
