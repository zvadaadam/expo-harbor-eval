# /// script
# dependencies = [
#   "harbor-rewardkit==0.1.7",
#   "tomli-w>=1.2.0",
# ]
# ///
"""Run an imported Expo code-gen rubric with explicit provider overrides."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__"})

# Environment scaffolding, not agent-authored content: docker mode copies it
# into /app (`COPY . /app/`) while local materialization excludes it, so the
# guards and baseline manifest must ignore it to behave the same in both.
SCAFFOLDING_FILES = frozenset(
    {"Dockerfile", "docker-compose.yaml", "docker-compose.yml"}
)


def _submitted_files(workspace: Path) -> list[Path]:
    files = []
    for path in sorted(workspace.rglob("*")):
        relative_parts = path.relative_to(workspace).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative_parts):
            continue
        if path.is_file() and path.name not in SCAFFOLDING_FILES:
            files.append(path)
    return files


def submission_directories(workspace: Path) -> list[str]:
    """Return directories Rewardkit should scan for submitted files."""
    directories = {workspace}
    for path in _submitted_files(workspace):
        directories.add(path.parent)
    return [str(path) for path in sorted(directories)]


def submission_manifest(workspace: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in _submitted_files(workspace)
    }


def guard_reason(rubric_source: Path, workspace: Path) -> str | None:
    """Deterministic zero-reward guards that run before any judge call.

    An empty workspace, or one byte-identical to the imported baseline,
    cannot satisfy any criterion. Scoring these without a judge keeps
    negative criteria ("must not use X") from passing vacuously on absent
    code and keeps a misfiring judge from awarding reward to a no-op.
    """
    submitted = submission_manifest(workspace)
    if not submitted:
        return "Empty submission: the workspace contains no reviewable files."
    # Every expo-codegen task ships the manifest (enforced by test_task_sync);
    # a missing one is a broken task and must fail loudly, not skip the guard.
    manifest_path = rubric_source / "baseline-manifest.json"
    baseline = json.loads(manifest_path.read_text())["files"]
    if submitted == baseline:
        return (
            "Unchanged submission: every workspace file is byte-identical "
            "to the task's starting environment."
        )
    return None


def write_guard_result(
    rubric_source: Path,
    output: Path,
    reason: str,
) -> dict[str, float]:
    """Write a zero reward in the same shape Rewardkit produces."""
    config: dict[str, Any] = tomllib.loads(
        (rubric_source / "rubric.toml").read_text()
    )
    criteria = [
        {
            "id": criterion["id"],
            "name": criterion["name"],
            "value": 0.0,
            "raw": "no",
            "weight": float(criterion.get("weight", 1.0)),
            "description": criterion["description"],
            "reasoning": f"Deterministic guard: {reason}",
        }
        for criterion in config["criterion"]
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"reward": 0.0}, indent=2) + "\n")
    (output.parent / "reward-details.json").write_text(
        json.dumps(
            {"reward": {"score": 0.0, "criteria": criteria, "guard": reason}},
            indent=2,
        )
        + "\n"
    )
    return {"reward": 0.0}


def prepare_rubric(
    source_dir: Path,
    destination_dir: Path,
    workspace: Path,
    judge_override: str | None,
    model_override: str | None,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    source_toml = source_dir / "rubric.toml"
    config: dict[str, Any] = tomllib.loads(source_toml.read_text())
    judge = config["judge"]
    judge["files"] = submission_directories(workspace)
    if judge_override:
        judge["judge"] = judge_override
    if model_override:
        judge["model"] = model_override

    # Rewardkit names a judge reward after the toml file stem, and Harbor's
    # headline metric convention is the "reward" key, so the prepared copy
    # must be reward.toml regardless of the source rubric's file name.
    destination_toml = destination_dir / "reward.toml"
    destination_toml.write_text(tomli_w.dumps(config))
    shutil.copy2(source_dir / "judge-prompt.md", destination_dir / "judge-prompt.md")
    return destination_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rubric", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    reason = guard_reason(args.rubric, args.workspace)
    if reason is not None:
        print(write_guard_result(args.rubric, args.output, reason))
        return

    from rewardkit.runner import run

    with tempfile.TemporaryDirectory(prefix="expo-harbor-rubric-") as temporary:
        prepared = prepare_rubric(
            args.rubric,
            Path(temporary),
            args.workspace,
            os.getenv("REWARDKIT_JUDGE") or None,
            os.getenv("REWARDKIT_MODEL") or None,
        )
        scores = run(prepared, workspace=args.workspace, output=args.output)
    print(scores)


if __name__ == "__main__":
    main()
