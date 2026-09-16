# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "harbor-rewardkit @ git+https://github.com/harbor-framework/harbor.git@cfc54c995e90cd438deb862189a58053b9d89fd3#subdirectory=packages/rewardkit",
#   "tomli-w>=1.2.0",
# ]
# ///
"""Run an Expo coding rubric with explicit provider overrides."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
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
        if any(part in SKIP_DIRS or (part.startswith(".") and part != ".well-known") for part in relative_parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinked submissions are not supported: {path}")
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
    # Validate before applying overrides or invoking a provider. This comes
    # from the pinned upstream Rewardkit revision, not a parallel schema.
    from rewardkit.models import JudgeTomlConfig
    JudgeTomlConfig.model_validate(config)
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


def reject_judge_errors(output: Path) -> None:
    """A judge timeout is an execution error, not a valid zero for the app."""
    details = json.loads((output.parent / "reward-details.json").read_text())
    def errors_in(value):
        if isinstance(value, dict):
            if value.get("error"):
                yield str(value["error"])
            for child in value.values():
                yield from errors_in(child)
        elif isinstance(value, list):
            for child in value:
                yield from errors_in(child)

    errors = list(errors_in(details))
    if errors:
        # Keep the detailed evidence, but never publish a candidate score for
        # an unsuccessful judge. Harbor will record the verifier exception.
        output.unlink(missing_ok=True)
        raise RuntimeError("Source judge failed: " + "; ".join(dict.fromkeys(errors)))


def behavior_spec(rubric: Path) -> dict | None:
    path = rubric / "behavior.json"
    return json.loads(path.read_text()) if path.is_file() else None


def run_behavior(rubric: Path, workspace: Path, output: Path) -> dict:
    """Run a trusted contract with no inherited model credentials or Node hooks."""
    spec = behavior_spec(rubric)
    if spec is None:
        raise ValueError(f"No behavioral contract for {rubric.parent.parent.name}")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js 24+ is required for behavioral verification")
    script = (rubric.parent / spec["script"]).resolve()
    if not script.is_relative_to(rubric.parent.resolve()):
        raise ValueError("Behavior script must be inside the trusted tests directory")
    workspace = workspace.resolve()
    entry = workspace / spec["entrypoint"]
    if not entry.resolve().is_relative_to(workspace):
        raise ValueError("Behavior entrypoint escapes the submitted workspace")
    completed = subprocess.run(
        [node, "--permission", f"--allow-fs-read={script}",
         f"--allow-fs-read={workspace}", str(script), str(entry)],
        capture_output=True, text=True, timeout=30,
        env={"PATH": os.defpath},
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / "behavior-stdout.txt").write_text(completed.stdout)
    (output.parent / "behavior-stderr.txt").write_text(completed.stderr)
    if completed.returncode:
        raise RuntimeError(f"Behavior verifier exited {completed.returncode}: {completed.stderr[-500:]}")
    evidence = json.loads(completed.stdout)
    failed = evidence.get("failedGroups")
    if (evidence.get("checks") != spec["checks"] or not isinstance(failed, list)
            or any(not isinstance(key, str) for key in failed)
            or len(failed) != len(set(failed)) or not set(failed) <= set(spec["criteria"])):
        raise ValueError("Behavior verifier returned incomplete or invalid evidence")
    config = tomllib.loads((rubric / "rubric.toml").read_text())
    definitions = {c["id"]: c for c in config["criterion"]}
    rows = [{**definitions[key], "value": float(key not in failed),
             "raw": "no" if key in failed else "yes", "evaluator": "behavior",
             "reasoning": f"Executed {evidence['checks']} contract cases; "
                          + ("this group failed." if key in failed else "this group passed.")}
            for key in spec["criteria"]]
    result = {"score": float(not failed), "criteria": rows, "evidence": evidence,
              "required_criteria": list(definitions),
              "entrypoint_sha256": hashlib.sha256(entry.read_bytes()).hexdigest() if entry.is_file() else None}
    (output.parent / "behavior-details.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def apply_behavior(output: Path, behavior: dict, *, only: bool = False) -> dict[str, float]:
    """Keep source review visible; require every effective criterion to pass."""
    if only:
        detail = {**behavior, "measurement": "policy-behavior", "aggregation": "all-pass"}
        scores = {"reward": behavior["score"]}
        details = {"reward": detail}
    else:
        details = json.loads((output.parent / "reward-details.json").read_text())
        source = details["reward"]
        source_ids = [row.get("id", row.get("name")) for row in source["criteria"]]
        if (set(source_ids) != set(behavior["required_criteria"]) or len(source_ids) != len(set(source_ids))
                or any(isinstance(row.get("value"), bool) or row.get("value") not in (0, 1)
                       for row in source["criteria"])):
            raise ValueError("Source judge must return every required binary criterion exactly once")
        replacements = {row["id"]: row for row in behavior["criteria"]}
        rows = [replacements.get(row.get("id", row.get("name")), row) for row in source["criteria"]]
        if not set(replacements) <= {row.get("id", row.get("name")) for row in source["criteria"]}:
            raise ValueError("Behavior criteria do not match the source rubric")
        score = float(all(row["value"] == 1 for row in rows))
        scores = {"reward": score, "source_review": source["score"], "policy_behavior": behavior["score"]}
        details = {"reward": {"score": score, "criteria": rows, "aggregation": "all-pass",
                               "measurement": "source-and-policy"},
                   "source_review": source, "policy_behavior": behavior}
    output.write_text(json.dumps(scores, indent=2) + "\n")
    (output.parent / "reward-details.json").write_text(json.dumps(details, indent=2) + "\n")
    return scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rubric", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--behavior-only", action="store_true", help="Execute the policy contract without a source judge")
    args = parser.parse_args()

    # Stale scores must not survive an interrupted or failed regrade.
    args.output.unlink(missing_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    (args.output.parent / "submission-manifest.json").write_text(
        json.dumps({"files": submission_manifest(args.workspace)}, indent=2) + "\n"
    )
    from rewardkit.models import JudgeTomlConfig
    JudgeTomlConfig.model_validate(tomllib.loads((args.rubric / "rubric.toml").read_text()))
    spec = behavior_spec(args.rubric)
    if args.behavior_only and spec is None:
        raise ValueError("--behavior-only requires a declared behavioral contract")

    reason = guard_reason(args.rubric, args.workspace)
    if reason is not None:
        print(write_guard_result(args.rubric, args.output, reason))
        return

    behavior = run_behavior(args.rubric, args.workspace, args.output) if spec else None
    if args.behavior_only:
        print(apply_behavior(args.output, behavior, only=True))
        return
    if behavior is not None and behavior["score"] == 0:
        # A failed required policy proves the combined task failed. Preserve
        # the known evidence and explicitly leave source review unperformed.
        scores = {"reward": 0.0, "policy_behavior": 0.0}
        detail = {"score": 0.0, "criteria": behavior["criteria"],
                  "measurement": "source-and-policy", "aggregation": "all-pass",
                  "source_review_skipped": "Required policy contract failed."}
        args.output.write_text(json.dumps(scores, indent=2) + "\n")
        (args.output.parent / "reward-details.json").write_text(
            json.dumps({"reward": detail, "policy_behavior": behavior}, indent=2) + "\n"
        )
        print(scores)
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
        reject_judge_errors(args.output)
        if behavior is not None:
            try:
                scores = apply_behavior(args.output, behavior)
            except Exception:
                args.output.unlink(missing_ok=True)
                raise
    print(scores)


if __name__ == "__main__":
    main()
