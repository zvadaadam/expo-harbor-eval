from __future__ import annotations

import json
import tomllib
from pathlib import Path

from expo_harbor_evals.codegen_adapter import _task_dir_name, import_eval
from expo_harbor_evals.codegen_reference_check import compare_reference
from expo_harbor_evals.codegen_rewardkit_runner import (
    guard_reason,
    prepare_rubric,
    write_guard_result,
)


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


def test_task_names_drop_vendor_and_slug_repetition() -> None:
    assert (
        _task_dir_name("evals/expo-ui/02-rn-expo-ui-bottom-sheet-controlled")
        == "expo-ui-02-bottom-sheet-controlled"
    )
    assert (
        _task_dir_name("evals/expo-sdk/04-rn-expo-image-picker-canceled-assets-guard")
        == "expo-sdk-04-image-picker-canceled-assets-guard"
    )
    assert (
        _task_dir_name(
            "evals/expo-router/02-rn-expo-router-stack-layout-not-native-stack-import"
        )
        == "expo-router-02-stack-layout-not-native-stack-import"
    )


def test_import_eval_generates_a_harbor_task(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    relative = _write_upstream_eval(upstream)

    imported = import_eval(upstream, tmp_path / "tasks", relative, "abc123")

    assert imported.requirement_count == 1
    assert imported.task_name == "expo-sdk-99-example"
    task = imported.output_path
    assert (task / "environment" / "App.tsx").read_text() == "export default null\n"
    assert (task / "solution" / "reference" / "App.tsx").exists()
    assert (task / "tests" / "reference" / "App.tsx").exists()

    task_config = tomllib.loads((task / "task.toml").read_text())
    assert task_config["task"]["name"] == "expo-harbor/expo-sdk-99-example"
    assert task_config["metadata"]["family"] == "expo-codegen"
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

    manifest = json.loads(
        (task / "tests" / "requirements" / "baseline-manifest.json").read_text()
    )
    assert set(manifest["files"]) == {"App.tsx"}

    marker = json.loads((task / ".expo-codegen-generated.json").read_text())
    assert marker["upstream_eval"] == relative


def test_guards_zero_empty_and_unchanged_submissions(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    relative = _write_upstream_eval(upstream)
    task = import_eval(upstream, tmp_path / "tasks", relative, "abc123").output_path
    rubric_dir = task / "tests" / "requirements"

    empty = tmp_path / "empty"
    empty.mkdir()
    assert guard_reason(rubric_dir, empty) is not None

    unchanged = tmp_path / "unchanged"
    unchanged.mkdir()
    (unchanged / "App.tsx").write_text("export default null\n")
    (unchanged / "Dockerfile").write_text("FROM scratch\n")  # scaffolding ignored
    assert guard_reason(rubric_dir, unchanged) is not None

    solved = tmp_path / "solved"
    solved.mkdir()
    (solved / "App.tsx").write_text("export default 42\n")
    assert guard_reason(rubric_dir, solved) is None

    output = tmp_path / "logs" / "reward.json"
    scores = write_guard_result(rubric_dir, output, "Empty submission: test.")
    assert scores == {"reward": 0.0}
    assert json.loads(output.read_text()) == {"reward": 0.0}
    details = json.loads((output.parent / "reward-details.json").read_text())
    assert details["reward"]["score"] == 0.0
    assert details["reward"]["guard"].startswith("Empty submission")
    assert [c["id"] for c in details["reward"]["criteria"]] == ["returns-value"]


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
    # The prepared file must be reward.toml: rewardkit keys the reward on the
    # toml stem and Harbor's headline metric key is "reward".
    assert not (prepared / "rubric.toml").exists()
    rubric = tomllib.loads((prepared / "reward.toml").read_text())

    assert rubric["judge"]["judge"] == "openai/judge-model"
    assert rubric["judge"]["files"] == [str(workspace), str(nested)]
