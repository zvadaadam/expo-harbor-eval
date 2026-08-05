"""Every task must carry valid, controlled metadata (supabase/evals-style)."""

from __future__ import annotations

from pathlib import Path

from expo_harbor_evals.metadata import validate_task_metadata

TASKS = Path(__file__).resolve().parent.parent / "tasks"


def test_all_tasks_have_valid_metadata() -> None:
    task_tomls = sorted(TASKS.rglob("task.toml"))
    assert task_tomls, "expected tasks"
    failures = {
        toml.parent.name: problems
        for toml in task_tomls
        if (problems := validate_task_metadata(toml))
    }
    assert not failures, f"metadata violations: {failures}"
