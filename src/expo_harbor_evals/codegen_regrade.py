"""Regrade saved coding submissions through Harbor without rerunning the agent."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from expo_harbor_evals.codegen_rewardkit_runner import behavior_spec, submission_manifest


def recover_legacy_trial(source: Path, destination: Path, audit: Path, task: Path) -> Path:
    """Recover only source bytes proven by the original pilot's tracked hashes.

    The new artifact manifest belongs to the recovered copy. Original trial
    records are never rewritten to pretend they collected artifacts earlier.
    """
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("Recovered trial must be outside the original trial")
    if destination.exists():
        raise FileExistsError(f"Recovery destination already exists: {destination}")
    records = json.loads(audit.read_text())["trials"]
    matches = [row for row in records if row.get("trial") and Path(row["trial"]).name == source.name]
    if len(matches) != 1 or matches[0].get("task") != task.name:
        raise ValueError("Legacy audit must identify this task and trial exactly once")
    expected = matches[0].get("source_sha256")
    workspace = source / "_local_env/app"
    actual = submission_manifest(workspace)
    if not expected or actual != expected:
        raise ValueError("Retained candidate does not match the recorded source hashes")
    result_file = source / "result.json"
    result = json.loads(result_file.read_text())
    if result.get("exception_info") or not result.get("finished_at"):
        raise ValueError("Legacy recovery requires a completed, successful execution")
    config = tomllib.loads((task / "task.toml").read_text())
    artifact = next(row for row in config["artifacts"] if row["source"] == "/app")
    destination.mkdir(parents=True)
    for name in ("result.json", "config.json", "lock.json", "evaluation.json"):
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    for name in ("agent", "artifacts"):
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name)
    copied = destination / "artifacts" / artifact["destination"]
    if copied.exists():
        raise ValueError("Legacy source already has candidate artifacts; use it directly")
    copied.mkdir(parents=True)
    for name in actual:
        target = copied / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workspace / name, target)
    if submission_manifest(copied) != expected:
        raise ValueError("Candidate changed while recovering its artifacts")
    manifest_path = destination / "artifacts/manifest.json"
    entries = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    entries.append({"source": "/app", "destination": "artifacts/" + artifact["destination"],
                    "type": "directory", "status": "ok", "service": None,
                    "exclude": artifact["exclude"]})
    manifest_path.write_text(json.dumps(entries, indent=2) + "\n")
    provenance = {"operation": "recover-retained-candidate", "source_trial": str(source),
                  "source_result_sha256": hashlib.sha256(result_file.read_bytes()).hexdigest(),
                  "audit": str(audit.resolve()), "audit_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
                  "files": actual}
    (destination / "recovery.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="One completed Harbor trial")
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Parent directory for the new regrade")
    parser.add_argument("--mode", choices=("behavior", "judge", "reference"), default="behavior")
    parser.add_argument("--legacy-audit", type=Path, help="Original tracked pilot summary containing source_sha256")
    parser.add_argument("--judge")
    parser.add_argument("--model")
    parser.add_argument("--environment", default="expo_harbor_evals.mac_sandbox_env:MacSandboxEnvironment")
    args = parser.parse_args()
    task, source, output = args.task.resolve(), args.source.resolve(), args.output.resolve()
    if args.mode == "behavior" and behavior_spec(task / "tests/requirements") is None:
        parser.error("Behavior mode requires a declared policy contract")
    from harbor.trial.regrade import check_task_regradable
    if error := check_task_regradable(task):
        parser.error(error)
    manifest_path = source / "artifacts/manifest.json"
    entries = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    if not any(row.get("source") == "/app" for row in entries):
        if not args.legacy_audit:
            parser.error("Source did not collect /app. Supply --legacy-audit to recover a hash-verified retained candidate.")
        source = recover_legacy_trial(source, output / ".sources" / source.name, args.legacy_audit, task)
    command = [sys.executable, "-c", "from harbor.cli.main import app; app()",
               "trial", "regrade", str(source), "--task-path", str(task),
               "--env", args.environment, "--trials-dir", str(output),
               "--trial-name", source.name + "-regrade",
               "--ve", "EXPO_EVAL_VERIFIER_MODE=" + args.mode]
    for key, value in (("REWARDKIT_JUDGE", args.judge), ("REWARDKIT_MODEL", args.model)):
        if value:
            command += ["--ve", key + "=" + value]
    completed = subprocess.run(command)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    result_file = output / (source.name + "-regrade") / "result.json"
    result = json.loads(result_file.read_text())
    if result.get("exception_info") or not result.get("verifier_result", {}).get("rewards"):
        raise SystemExit("Regrade did not produce a valid score; inspect " + str(result_file))


if __name__ == "__main__":
    main()
