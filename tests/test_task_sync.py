"""Guard against drift between src/ modules and their per-task vendored copies."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

from expo_harbor_evals.codegen_adapter import baseline_manifest
from expo_harbor_evals.scoring import normalize_evaluator_result

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "expo_harbor_evals"
TASKS = REPO_ROOT / "tasks"

VENDORED_CODEGEN_SCRIPTS = {
    "run_rewardkit.py": "codegen_rewardkit_runner.py",
    "reference_check.py": "codegen_reference_check.py",
}


def codegen_task_dirs() -> list[Path]:
    dirs = [
        toml.parent
        for toml in sorted(TASKS.glob("*/task.toml"))
        if tomllib.loads(toml.read_text())["metadata"].get("family")
        == "expo-codegen"
    ]
    assert dirs, "expected imported expo-codegen tasks"
    return dirs


def test_codegen_task_scripts_match_src_copies() -> None:
    for task_dir in codegen_task_dirs():
        for vendored_name, src_name in VENDORED_CODEGEN_SCRIPTS.items():
            vendored = task_dir / "tests" / vendored_name
            expected = (SRC / src_name).read_text()
            assert vendored.read_text() == expected, (
                f"{vendored} drifted from src/expo_harbor_evals/{src_name}; "
                "re-run make codegen-import or copy the src file over it"
            )


def test_codegen_environment_is_not_the_solution() -> None:
    """A baseline that already matches the reference makes a no-op score 1.0.

    This tripwire exists because two task environments were once silently
    overwritten with their reference solutions mid-experiment.
    """
    for task_dir in codegen_task_dirs():
        reference = task_dir / "solution" / "reference"
        reference_files = sorted(p for p in reference.rglob("*") if p.is_file())
        assert reference_files, f"{task_dir.name} has no reference solution"
        solved = all(
            (task_dir / "environment" / p.relative_to(reference)).exists()
            and (task_dir / "environment" / p.relative_to(reference)).read_bytes()
            == p.read_bytes()
            for p in reference_files
        )
        assert not solved, (
            f"{task_dir.name}: environment/ is byte-identical to "
            "solution/reference — the task ships already solved"
        )


def test_codegen_baseline_manifest_matches_environment() -> None:
    """The guard manifest must describe the exact environment agents receive."""
    for task_dir in codegen_task_dirs():
        manifest_path = (
            task_dir / "tests" / "requirements" / "baseline-manifest.json"
        )
        assert manifest_path.exists(), f"{task_dir.name} is missing its manifest"
        stored = json.loads(manifest_path.read_text())["files"]
        actual = baseline_manifest(task_dir / "environment")
        assert stored == actual, (
            f"{task_dir.name}: baseline-manifest.json disagrees with "
            "environment/ — re-run make codegen-import or regenerate the manifest"
        )


def test_simbench_tasks_share_their_golden_app() -> None:
    """Tasks built on the same golden app must ship identical app sources."""
    groups: dict[str, list] = {}
    for task_dir in sorted(TASKS.glob("simbench-ios-*")):
        sources = sorted((task_dir / "environment" / "app-src").glob("*.swift"))
        assert sources, f"{task_dir.name} has no app source"
        groups.setdefault(sources[0].name, []).append(task_dir)
    assert len(groups) >= 2, "expected GoldenNotes and GoldenLab task groups"
    for app_name, task_dirs in groups.items():
        reference = task_dirs[0] / "environment"
        for task_dir in task_dirs[1:]:
            for rel in (f"app-src/{app_name}", "app-src/Info.plist", "driver/setup.sh"):
                assert (task_dir / "environment" / rel).read_text() == (
                    reference / rel
                ).read_text(), (
                    f"{task_dir.name}/environment/{rel} drifted from "
                    f"{task_dirs[0].name}; tasks sharing a golden app must be identical"
                )


def test_vendored_score_result_matches_scoring_module() -> None:
    vendored_path = TASKS / "expo-mobile-eval-import" / "tests" / "score_result.py"
    spec = importlib.util.spec_from_file_location("vendored_score_result", vendored_path)
    assert spec and spec.loader
    vendored = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vendored)

    fixtures = sorted(
        (TASKS / "expo-mobile-eval-import" / "tests" / "fixtures").glob("*.json")
    )
    assert fixtures, "expected evaluator result fixtures"
    for fixture in fixtures:
        raw = json.loads(fixture.read_text())
        assert vendored.normalize(raw) == normalize_evaluator_result(raw), (
            f"vendored score_result.py disagrees with scoring.py on {fixture.name}"
        )
