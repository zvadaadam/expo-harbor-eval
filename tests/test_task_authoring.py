"""Integrity guards for hand-authored codegen tasks and the triage ledger."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from expo_harbor_evals.codegen_calibrate import codegen_task_dirs

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS = REPO_ROOT / "tasks"


def test_codegen_environment_files_are_tracked() -> None:
    """Gitignore rules must not silently drop task environment files.

    The slider task vendors node_modules content that the repo-root dist/
    ignore rule once swallowed: the file existed on the author's disk (so
    calibration passed) while every fresh checkout shipped the task without
    the file its instruction points at.
    """
    tracked = set(
        subprocess.run(
            ["git", "ls-files", "tasks"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    )
    for task_dir in codegen_task_dirs(TASKS):
        for path in (task_dir / "environment").rglob("*"):
            if path.is_file() and path.name != ".DS_Store":
                relative = path.relative_to(REPO_ROOT).as_posix()
                assert relative in tracked, (
                    f"{relative} exists on disk but is not tracked by git — "
                    "check .gitignore rules"
                )


def test_requirements_count_matches_rubric() -> None:
    for task_dir in codegen_task_dirs(TASKS):
        metadata = tomllib.loads((task_dir / "task.toml").read_text())["metadata"]
        rubric = tomllib.loads(
            (task_dir / "tests" / "requirements" / "rubric.toml").read_text()
        )
        assert metadata["requirements"] == len(rubric["criterion"]), (
            f"{task_dir.name}: metadata.requirements={metadata['requirements']} "
            f"but rubric.toml declares {len(rubric['criterion'])} criteria"
        )


def test_slider_task_vendored_wrapper_is_present() -> None:
    """feedback-05's premise is reading the installed wrapper source."""
    wrapper = (
        TASKS
        / "codegen"
        / "feedback-05-slider-relative-recenter"
        / "environment"
        / "node_modules"
        / "@react-native-community"
        / "slider"
        / "dist"
        / "Slider.js"
    )
    assert wrapper.exists(), "vendored dist/Slider.js is missing"
    assert (
        "passedValue=Number.isNaN(value)||!value?undefined:value"
        in wrapper.read_text()
    ), "vendored wrapper lost the load-bearing falsy-value coercion"


def test_triage_ledger_matches_task_dirs() -> None:
    """A ledger row that says a task exists (or is planned) must stay true."""
    ledger = (TASKS / "TRIAGE.md").read_text()
    rows_checked = 0
    for row in re.findall(r"^\|.*\|$", ledger, flags=re.M):
        where = row.rsplit("|", 2)[-2].strip()
        match = re.search(r"feedback-(\d{2})(-[a-z0-9-]+)?", where)
        if not match:
            continue
        rows_checked += 1
        number, slug = match.group(1), match.group(2)
        existing = sorted((TASKS / "codegen").glob(f"feedback-{number}-*"))
        if "(planned)" in where:
            assert not existing, (
                f"ledger says feedback-{number} is planned, "
                f"but {existing[0].name} exists — update the row"
            )
        elif slug:
            task_dir = TASKS / "codegen" / f"feedback-{number}{slug}"
            assert (task_dir / "task.toml").exists(), (
                f"ledger points at {task_dir.name} but its task.toml is missing"
            )
        else:
            assert existing, (
                f"ledger references feedback-{number} but no such task dir exists"
            )
    assert rows_checked >= 7, "triage ledger rows went missing"
