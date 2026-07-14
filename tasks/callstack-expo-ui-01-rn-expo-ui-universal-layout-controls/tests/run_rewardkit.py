# /// script
# dependencies = [
#   "harbor-rewardkit==0.1",
#   "tomli-w>=1.2.0",
# ]
# ///
"""Run an imported Callstack rubric with explicit provider overrides."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__"})


def submission_directories(workspace: Path) -> list[str]:
    """Return directories Rewardkit should scan for submitted files."""
    directories = {workspace}
    for path in workspace.rglob("*"):
        relative_parts = path.relative_to(workspace).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative_parts):
            continue
        if path.is_file():
            directories.add(path.parent)
    return [str(path) for path in sorted(directories)]


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

    destination_toml = destination_dir / "rubric.toml"
    destination_toml.write_text(tomli_w.dumps(config))
    shutil.copy2(source_dir / "judge-prompt.md", destination_dir / "judge-prompt.md")
    return destination_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rubric", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

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
