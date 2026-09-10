from __future__ import annotations

import json
import tomllib
from pathlib import Path

from expo_harbor_evals.codegen_reference_check import compare_reference
from expo_harbor_evals.codegen_rewardkit_runner import (
    guard_reason,
    submission_manifest,
    prepare_rubric,
    write_guard_result,
)


def test_guards_zero_empty_and_unchanged_submissions(tmp_path: Path) -> None:
    rubric_dir = tmp_path / "requirements"
    rubric_dir.mkdir()
    (rubric_dir / "rubric.toml").write_text(
        '[[criterion]]\nname="returns-value"\nid="returns-value"\n'
        'description="Must return the expected value."\ntype="binary"\nweight=2\n'
    )
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "App.tsx").write_text("export default null\n")
    (rubric_dir / "baseline-manifest.json").write_text(
        json.dumps({"files": submission_manifest(baseline)})
    )

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
