from __future__ import annotations

import json
import tomllib
from pathlib import Path

from expo_harbor_evals.callstack_adapter import import_eval
from expo_harbor_evals.callstack_reference_check import compare_reference
from expo_harbor_evals.callstack_rewardkit_runner import prepare_rubric


def _write_upstream_eval(root: Path) -> str:
    relative = "evals/expo-sdk/99-example"
    eval_root = root / relative
    (eval_root / "app").mkdir(parents=True)
    (eval_root / "reference").mkdir()
    (eval_root / "app" / "App.tsx").write_text("export default null\n")
    (eval_root / "reference" / "App.tsx").write_text("export default 42\n")
    (eval_root / "prompt.md").write_text("Implement the example.")
    (eval_root / "requirements.yaml").write_text(
        """version: 1
requirements:
  - id: returns-value
    description: Must return the expected value.
    weight: 2
"""
    )
    return relative


def test_import_eval_generates_a_harbor_task(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    relative = _write_upstream_eval(upstream)

    imported = import_eval(upstream, tmp_path / "tasks", relative, "abc123")

    assert imported.requirement_count == 1
    task = imported.output_path
    assert (task / "environment" / "App.tsx").read_text() == "export default null\n"
    assert (task / "solution" / "reference" / "App.tsx").exists()
    assert (task / "tests" / "reference" / "App.tsx").exists()

    task_config = tomllib.loads((task / "task.toml").read_text())
    assert task_config["metadata"]["upstream_commit"] == "abc123"
    assert task_config["metadata"]["requirements"] == 1

    rubric = tomllib.loads(
        (task / "tests" / "requirements" / "rubric.toml").read_text()
    )
    assert rubric["criterion"] == [
        {
            "name": "returns-value",
            "id": "returns-value",
            "description": "Must return the expected value.",
            "type": "binary",
            "weight": 2,
        }
    ]

    marker = json.loads((task / ".callstack-generated.json").read_text())
    assert marker["upstream_eval"] == relative


def test_reference_check_is_exact_for_expected_files_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    reference = tmp_path / "reference"
    workspace.mkdir()
    reference.mkdir()
    (reference / "App.tsx").write_text("expected\n")
    (workspace / "App.tsx").write_text("expected\n")
    (workspace / "extra.ts").write_text("allowed extra\n")

    score, results = compare_reference(workspace, reference)

    assert score == 1.0
    assert [result.status for result in results] == ["matched"]


def test_prepare_rubric_applies_provider_and_recursive_file_overrides(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    nested = workspace / "routes"
    source.mkdir()
    nested.mkdir(parents=True)
    (workspace / "App.tsx").write_text("root\n")
    (nested / "details.tsx").write_text("nested\n")
    (source / "judge-prompt.md").write_text("{criteria}\n")
    (source / "rubric.toml").write_text(
        """[judge]
judge = "anthropic/default"
files = ["/app"]
prompt_template = "judge-prompt.md"

[[criterion]]
name = "works"
description = "Must work."
type = "binary"
"""
    )

    prepared = prepare_rubric(
        source,
        tmp_path / "prepared",
        workspace,
        "openai/judge-model",
        None,
    )
    rubric = tomllib.loads((prepared / "rubric.toml").read_text())

    assert rubric["judge"]["judge"] == "openai/judge-model"
    assert rubric["judge"]["files"] == [str(workspace), str(nested)]
