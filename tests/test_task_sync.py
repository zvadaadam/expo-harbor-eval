"""Guard against drift between src/ modules and their per-task vendored copies."""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path

import yaml

from expo_harbor_evals import codegen_scaffold
from expo_harbor_evals.codegen_calibrate import codegen_task_dirs
from expo_harbor_evals.codegen_rewardkit_runner import submission_manifest
from expo_harbor_evals.mobile_eval import PROFILES

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "expo_harbor_evals"
TASKS = REPO_ROOT / "tasks"
JOBS = REPO_ROOT / "jobs"

VENDORED_CODEGEN_SCRIPTS = {
    "run_rewardkit.py": "codegen_rewardkit_runner.py",
    "reference_check.py": "codegen_reference_check.py",
}

# Scaffold files every expo-codegen task shares, for API exercises and
# field-report regressions: a template change must reach
# all of them or judge results stop being comparable across the family.
SCAFFOLD_TEMPLATES = {
    "tests/test.sh": "TEST_SH",
    "solution/solve.sh": "SOLUTION_SH",
    "tests/requirements/judge-prompt.md": "JUDGE_PROMPT",
    "environment/Dockerfile": "DOCKERFILE",
    "tests/Dockerfile": "VERIFIER_DOCKERFILE",
}


def test_job_groups_select_existing_tasks_and_keep_results_separate() -> None:
    expected = {"codegen": "codegen", "native": "codegen", "simbench": "simbench"}
    jobs = sorted(JOBS.rglob("*.yaml"))
    assert jobs
    for path in jobs:
        config = yaml.safe_load(path.read_text())
        assert path.parent.name in expected, f"Ungrouped job: {path}"
        assert config["jobs_dir"] == "runs", f"Job output would mix with configuration: {path}"
        assert config["datasets"], f"No task cohort: {path}"
        for dataset in config["datasets"]:
            family = expected[path.parent.name]
            assert dataset["path"] == f"tasks/{family}"
            available = {p.parent.name for p in (TASKS / family).glob("*/task.toml")}
            assert dataset.get("task_names"), f"Implicit unfrozen cohort: {path}"
            for name in dataset["task_names"]:
                matches = {task for task in available if fnmatch(task, name)}
                assert matches, f"Unknown task selector {name} in {path}"
                if path.parent.name == "native":
                    assert matches <= PROFILES.keys(), f"Native scenario missing for {matches}"
        mode = config.get("verifier", {}).get("env", {}).get("EXPO_EVAL_VERIFIER_MODE")
        if path.parent.name == "native":
            assert mode == "mobile"
        elif path.parent.name == "codegen":
            assert mode in ("judge", "reference", "behavior")


def test_native_profiles_reuse_existing_coding_tasks() -> None:
    runtime_tasks = {p.parents[2].name for p in (TASKS / "codegen").glob("*/tests/requirements/runtime.json")}
    assert runtime_tasks == set(PROFILES)
    for task in runtime_tasks:
        assert (TASKS / "codegen" / task / "task.toml").is_file()
        assert not (TASKS / "simbench" / task).exists()


def test_codegen_task_scripts_match_src_copies() -> None:
    for task_dir in codegen_task_dirs(TASKS):
        for vendored_name, src_name in VENDORED_CODEGEN_SCRIPTS.items():
            vendored = task_dir / "tests" / vendored_name
            expected = (SRC / src_name).read_text()
            if vendored_name == "run_rewardkit.py" and (task_dir / "tests/requirements/grading.json").is_file():
                assert (task_dir / "tests/source_runner.py").read_text() == expected
                expected = (REPO_ROOT / "graders/kit_runner.py").read_text()
            assert vendored.read_text() == expected, (
                f"{vendored} drifted from src/expo_harbor_evals/{src_name}; "
                "copy the canonical src file over the task copy"
            )


def test_codegen_scaffolding_matches_scaffold_templates() -> None:
    for task_dir in codegen_task_dirs(TASKS):
        for relative, constant in SCAFFOLD_TEMPLATES.items():
            actual = (task_dir / relative).read_text()
            assert actual == getattr(codegen_scaffold, constant), (
                f"{task_dir.name}/{relative} drifted from codegen_scaffold."
                f"{constant}; "
                "copy the canonical template over the task copy"
            )


def test_codegen_tests_reference_matches_solution_reference() -> None:
    """The judged oracle and the reference-mode oracle must be the same code."""
    for task_dir in codegen_task_dirs(TASKS):
        solution = task_dir / "solution" / "reference"
        vendored = task_dir / "tests" / "reference"
        solution_files = sorted(
            p.relative_to(solution) for p in solution.rglob("*") if p.is_file()
        )
        vendored_files = sorted(
            p.relative_to(vendored) for p in vendored.rglob("*") if p.is_file()
        )
        assert solution_files == vendored_files, (
            f"{task_dir.name}: tests/reference and solution/reference hold "
            "different file sets"
        )
        for relative in solution_files:
            assert (vendored / relative).read_bytes() == (
                solution / relative
            ).read_bytes(), (
                f"{task_dir.name}: tests/reference/{relative} drifted from "
                "solution/reference"
            )


def test_codegen_environment_is_not_the_solution() -> None:
    """A baseline that already matches the reference makes a no-op score 1.0.

    This tripwire exists because two task environments were once silently
    overwritten with their reference solutions mid-experiment.
    """
    for task_dir in codegen_task_dirs(TASKS):
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
    for task_dir in codegen_task_dirs(TASKS):
        manifest_path = (
            task_dir / "tests" / "requirements" / "baseline-manifest.json"
        )
        assert manifest_path.exists(), f"{task_dir.name} is missing its manifest"
        stored = json.loads(manifest_path.read_text())["files"]
        actual = submission_manifest(task_dir / "environment")
        assert stored == actual, (
            f"{task_dir.name}: baseline-manifest.json disagrees with "
            "environment/ — regenerate the baseline manifest after reviewing the source change"
        )


def test_simbench_tasks_share_their_golden_app() -> None:
    """Tasks built on the same golden app must ship identical app sources."""
    groups: dict[str, list] = {}
    for task_dir in sorted((TASKS / "simbench").glob("simbench-ios-*")):
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


def test_simbench_job_agents_stay_in_sync() -> None:
    """The same agent variant must be configured identically in every simbench job.

    Prefaces and tool lists are part of the experimental condition: if
    sonnet#agent-device drifts between ladder and flows, their numbers stop
    being comparable across tiers.
    """
    groups: dict[str, dict[str, dict]] = {}
    for job_path in sorted((JOBS / "simbench").glob("*.yaml")):
        for agent in yaml.safe_load(job_path.read_text())["agents"]:
            key = agent.get("model_name") or agent["name"]
            groups.setdefault(key, {})[job_path.name] = agent
    assert groups, "no agents found in jobs/simbench/*.yaml"
    for key, by_job in groups.items():
        job_names = sorted(by_job)
        reference = by_job[job_names[0]]
        for job_name in job_names[1:]:
            assert by_job[job_name] == reference, (
                f"agent {key!r} in {job_name} drifted from {job_names[0]}; "
                "the same variant must be identical in every simbench job"
            )
