"""Generate Harbor tasks from Callstack's React Native Expo evals."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

UPSTREAM_URL = "https://github.com/callstackincubator/evals"
DEFAULT_JUDGE = "anthropic/claude-sonnet-4-6"

DEFAULT_EVALS = (
    "evals/expo-sdk/04-rn-expo-image-picker-canceled-assets-guard",
    "evals/expo-sdk/10-rn-expo-notifications-listener-cleanup",
    "evals/expo-sdk/12-rn-expo-filesystem-object-api-read-write",
    "evals/expo-router/02-rn-expo-router-stack-layout-not-native-stack-import",
    "evals/expo-router/07-rn-expo-router-protected-routes-auth",
    "evals/expo-router/08-rn-expo-router-serializable-search-params",
    "evals/expo-ui/01-rn-expo-ui-universal-layout-controls",
    "evals/expo-ui/02-rn-expo-ui-bottom-sheet-controlled",
    "evals/expo-ui/06-rn-expo-ui-native-state-text-input",
)


@dataclass(frozen=True)
class Requirement:
    id: str
    description: str
    weight: float


@dataclass(frozen=True)
class ImportedTask:
    upstream_path: str
    task_name: str
    output_path: Path
    requirement_count: int


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _read_requirements(path: Path) -> list[Requirement]:
    raw: Any = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    rows = raw.get("requirements")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path} must contain non-empty requirements")

    requirements: list[Requirement] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Invalid requirement in {path}: {row!r}")
        requirement_id = row.get("id")
        description = row.get("description")
        weight = row.get("weight", 1.0)
        if not isinstance(requirement_id, str) or not requirement_id:
            raise ValueError(f"Requirement id must be a non-empty string in {path}")
        if requirement_id in seen:
            raise ValueError(f"Duplicate requirement id {requirement_id!r} in {path}")
        if not isinstance(description, str) or not description:
            raise ValueError(f"Requirement {requirement_id!r} has no description")
        if not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError(f"Requirement {requirement_id!r} has invalid weight")
        seen.add(requirement_id)
        requirements.append(Requirement(requirement_id, description, float(weight)))
    return requirements


def _task_dir_name(upstream_path: str) -> str:
    path = Path(upstream_path)
    if len(path.parts) != 3 or path.parts[0] != "evals":
        raise ValueError(f"Expected evals/<category>/<eval-id>, got {upstream_path!r}")
    category = path.parts[1]
    if category not in {"expo-sdk", "expo-router", "expo-ui"}:
        raise ValueError(f"Unsupported Callstack category: {category}")
    return f"callstack-{category}-{path.name}"


def _source_commit(source: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _render_task_toml(
    task_dir_name: str,
    upstream_path: str,
    commit: str,
    requirement_count: int,
) -> str:
    category = Path(upstream_path).parts[1]
    return f"""schema_version = "1.3"

[task]
name = {_toml_string(f"expo-harbor/{task_dir_name}")}
description = "Callstack React Native Expo eval adapted to Harbor."
authors = [{{ name = "Callstack React Native Evals contributors" }}]
keywords = ["react-native", "expo", "harbor", "callstack", "llm-judge"]

[metadata]
category = {_toml_string(category)}
difficulty = "mixed"
upstream_url = {_toml_string(UPSTREAM_URL)}
upstream_commit = {_toml_string(commit)}
upstream_eval = {_toml_string(upstream_path)}
upstream_license = "MIT"
requirements = {requirement_count}
verifier = "rewardkit-weighted-binary"

[agent]
timeout_sec = 900.0

[verifier]
timeout_sec = 900.0

[environment]
network_mode = "public"
build_timeout_sec = 600.0
workdir = "/app"
cpus = 2
memory_mb = 4096
storage_mb = 10240
"""


def _render_rubric(requirements: list[Requirement]) -> str:
    parts = [
        "[judge]",
        f"judge = {_toml_string(DEFAULT_JUDGE)}",
        'files = ["/app"]',
        'prompt_template = "judge-prompt.md"',
        "timeout = 300",
        'reasoning_effort = "medium"',
        "",
    ]
    for requirement in requirements:
        parts.extend(
            [
                "[[criterion]]",
                f"name = {_toml_string(requirement.id)}",
                f"id = {_toml_string(requirement.id)}",
                f"description = {_toml_string(requirement.description)}",
                'type = "binary"',
                f"weight = {requirement.weight:g}",
                "",
            ]
        )
    parts.extend(["[scoring]", 'aggregation = "weighted_mean"', ""])
    return "\n".join(parts)


JUDGE_PROMPT = """You are reviewing a React Native code submission against explicit acceptance criteria.
Decide pass or fail for every criterion using only the submitted files as evidence.

Rules:
- File paths are evidence for placement and naming requirements.
- Mark a criterion false when evidence is missing or contradictory.
- Accept any implementation that satisfies the criterion; do not require the reference solution's exact code.
- Keep reasoning concise, concrete, and technically specific.
- Return exactly one result for every declared criterion name.

{criteria}
"""


DOCKERFILE = """FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates \\
    curl \\
    git \\
    python3 \\
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY . /app/
"""


TEST_SH = """#!/usr/bin/env bash
set -euo pipefail

TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
APP_DIR="${HARBOR_APP_DIR:-/app}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"
MODE="${EXPO_EVAL_VERIFIER_MODE:-judge}"

mkdir -p "$LOGS_DIR/verifier"

case "$MODE" in
  reference)
    python3 "$TESTS_DIR/reference_check.py" \\
      "$APP_DIR" \\
      "$TESTS_DIR/reference" \\
      "$LOGS_DIR/verifier/reward.json" \\
      --details "$LOGS_DIR/verifier/reward-details.json"
    ;;
  judge)
    uv run "$TESTS_DIR/run_rewardkit.py" \\
      "$TESTS_DIR/requirements" \\
      "$APP_DIR" \\
      "$LOGS_DIR/verifier/reward.json"
    ;;
  *)
    echo "Unknown EXPO_EVAL_VERIFIER_MODE: $MODE" >&2
    exit 2
    ;;
esac

cat "$LOGS_DIR/verifier/reward.json"
"""


SOLUTION_SH = """#!/usr/bin/env bash
set -euo pipefail

SOLUTION_DIR="${HARBOR_SOLUTION_DIR:-/solution}"
APP_DIR="${HARBOR_APP_DIR:-/app}"

cp -R "$SOLUTION_DIR/reference/." "$APP_DIR/"
"""


def import_eval(
    source: Path,
    output_root: Path,
    upstream_path: str,
    commit: str,
) -> ImportedTask:
    eval_root = source / upstream_path
    app_dir = eval_root / "app"
    reference_dir = eval_root / "reference"
    requirements_path = eval_root / "requirements.yaml"
    prompt_path = eval_root / "prompt.md"
    for required in (app_dir, reference_dir, requirements_path, prompt_path):
        if not required.exists():
            raise FileNotFoundError(f"Missing required upstream path: {required}")

    requirements = _read_requirements(requirements_path)
    task_dir_name = _task_dir_name(upstream_path)
    destination = output_root / task_dir_name
    marker = destination / ".callstack-generated.json"
    if destination.exists():
        if not marker.exists():
            raise FileExistsError(
                f"Refusing to replace non-generated task directory: {destination}"
            )
        shutil.rmtree(destination)

    environment_dir = destination / "environment"
    solution_dir = destination / "solution"
    tests_dir = destination / "tests"
    rubric_dir = tests_dir / "requirements"
    for path in (environment_dir, solution_dir, tests_dir, rubric_dir):
        path.mkdir(parents=True, exist_ok=True)

    _copy_contents(app_dir, environment_dir)
    (environment_dir / "Dockerfile").write_text(DOCKERFILE)

    prompt = prompt_path.read_text().rstrip()
    (destination / "instruction.md").write_text(
        f"{prompt}\n\nWork in `/app`. Modify the existing files and add any files required "
        "to complete the task.\n"
    )
    (destination / "task.toml").write_text(
        _render_task_toml(
            task_dir_name,
            upstream_path,
            commit,
            len(requirements),
        )
    )

    _write_executable(solution_dir / "solve.sh", SOLUTION_SH)
    _copy_contents(reference_dir, solution_dir / "reference")

    _write_executable(tests_dir / "test.sh", TEST_SH)
    shutil.copy2(
        Path(__file__).with_name("callstack_reference_check.py"),
        tests_dir / "reference_check.py",
    )
    shutil.copy2(
        Path(__file__).with_name("callstack_rewardkit_runner.py"),
        tests_dir / "run_rewardkit.py",
    )
    _copy_contents(reference_dir, tests_dir / "reference")
    shutil.copy2(requirements_path, tests_dir / "upstream-requirements.yaml")
    (rubric_dir / "rubric.toml").write_text(_render_rubric(requirements))
    (rubric_dir / "judge-prompt.md").write_text(JUDGE_PROMPT)

    marker.write_text(
        json.dumps(
            {
                "upstream_url": UPSTREAM_URL,
                "upstream_commit": commit,
                "upstream_eval": upstream_path,
            },
            indent=2,
        )
        + "\n"
    )
    return ImportedTask(
        upstream_path=upstream_path,
        task_name=task_dir_name,
        output_path=destination,
        requirement_count=len(requirements),
    )


def discover_all_expo(source: Path) -> tuple[str, ...]:
    found = []
    for category in ("expo-router", "expo-sdk", "expo-ui"):
        for requirements in sorted(
            (source / "evals" / category).glob("*/requirements.yaml")
        ):
            found.append(requirements.parent.relative_to(source).as_posix())
    return tuple(found)


def write_attribution(
    source: Path,
    destination: Path,
    commit: str,
    imported: list[ImportedTask],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    license_path = source / "LICENSE"
    if license_path.exists():
        shutil.copy2(license_path, destination / "LICENSE")
    rows = "\n".join(f"- `{task.upstream_path}`" for task in imported)
    (destination / "UPSTREAM.md").write_text(
        f"""# Callstack React Native Evals

Source: {UPSTREAM_URL}

Pinned commit: `{commit}`

License: MIT; see `LICENSE` in this directory.

Imported evals:

{rows}
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("../callstack-evals"))
    parser.add_argument("--output", type=Path, default=Path("tasks"))
    parser.add_argument(
        "--attribution-dir",
        type=Path,
        default=Path("third_party/callstackincubator-evals"),
    )
    parser.add_argument("--eval", action="append", dest="evals")
    parser.add_argument("--all-expo", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    if args.all_expo and args.evals:
        parser.error("Use either --all-expo or --eval, not both")
    selected = (
        discover_all_expo(source)
        if args.all_expo
        else tuple(args.evals or DEFAULT_EVALS)
    )
    commit = _source_commit(source)
    imported = [
        import_eval(source, args.output, upstream_path, commit)
        for upstream_path in selected
    ]
    write_attribution(source, args.attribution_dir, commit, imported)

    requirement_total = sum(task.requirement_count for task in imported)
    print(
        f"Imported {len(imported)} Callstack Expo evals "
        f"with {requirement_total} requirements from {commit[:12]}."
    )


if __name__ == "__main__":
    main()
