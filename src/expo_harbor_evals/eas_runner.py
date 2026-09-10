"""Prepare, dispatch, retrieve, and cancel one EAS simbench calibration shard.

Only an allowlisted evaluator source payload is uploaded. Submission is never
retried automatically: an ambiguous response may represent a billed run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import time
import urllib.request
import uuid
from pathlib import Path, PurePosixPath

from dotenv import dotenv_values

from expo_harbor_evals.simbench_calibrate import FLOW_TASK, check_calibration
from expo_harbor_evals.simbench_evidence import digest, write_json

EAS = ["npx", "--yes", "eas-cli@23.2.0"]
WORKFLOW = ".eas/workflows/simbench.yml"
TERMINAL = {"SUCCESS", "FAILURE", "CANCELED"}
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def load_eas_config(directory: Path) -> None:
    """Load only controller settings; never evaluate dotenv values as shell code."""
    values = {}
    for name in (".env", ".env.local"):
        path = directory / name
        if path.is_file():
            values.update(dotenv_values(path, interpolate=False))
    for name in ("EXPO_TOKEN", "EAS_EVAL_PROJECT_ID"):
        if values.get(name):
            os.environ.setdefault(name, values[name])


def prepare(repo: Path, destination: Path, project_id: str, task: str, attempts: int,
            candidate: Path | None = None) -> dict:
    uuid.UUID(project_id)
    family = "codegen" if candidate is not None else "simbench"
    if Path(task).name != task or not (repo / "tasks" / family / task / "task.toml").is_file():
        raise ValueError("Unknown task in selected evaluation family")
    # The current shard is calibrated with agent-device; the vision oracle
    # needs Argent as well and belongs in a separately provisioned condition.
    if "vision-grid" in task:
        raise ValueError("The vision oracle needs Argent; this workflow provisions agent-device only")
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if candidate is not None and attempts != 1:
        raise ValueError("Submit one candidate trial per shard; repetitions need separate shards")
    destination.mkdir(parents=True, exist_ok=False)
    if candidate is not None:
        from expo_harbor_evals.mobile_eval import prepare as prepare_candidate
        prepare_candidate(task, candidate, destination / "candidate", repo=repo)
    paths = ["pyproject.toml", "uv.lock", "README.md", "NOTICE.md", WORKFLOW, "scripts/eas_simbench.py"]
    paths += [str(p.relative_to(repo)) for p in (repo / "src/expo_harbor_evals").glob("*.py")]
    paths += [str(p.relative_to(repo)) for p in (repo / "tasks" / family / task).rglob("*")
              if p.is_file() and "__pycache__" not in p.parts]
    if (repo / "suites/mobile-v2.json").exists():
        paths.append("suites/mobile-v2.json")
        paths += list(json.loads((repo / "suites/mobile-v2.json").read_text())["engine"])
    files = {}
    for name in sorted(set(paths)):
        source = repo / name
        if source.is_symlink():
            raise ValueError(f"Refusing a source symlink: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files[name] = digest(target.read_bytes())
    for path in sorted((destination / "candidate").rglob("*")) if candidate is not None else []:
        if path.is_file():
            files[str(path.relative_to(destination))] = digest(path.read_bytes())
    spec = {"schema_version": 1, "kind": "candidate-eas-shard" if candidate is not None else "simbench-eas-shard", "shard_id": str(uuid.uuid4()),
            "project_id": project_id, "task": task, "attempts": attempts, "files": files}
    write_json(destination / "eval-source.json", spec)
    write_json(destination / "app.json", {"expo": {"name": "Harbor Evals", "slug": "harbor-evals",
               "extra": {"eas": {"projectId": project_id}}}})
    write_json(destination / "package.json", {"name": "harbor-evals", "version": "0.0.0", "private": True})
    (destination / ".gitignore").write_text(".venv/\neval-output/\n*.tar.gz\n.env\n.env.*\n")
    subprocess.run(["git", "init", "-q", str(destination)], check=True)
    # A real HEAD makes the prepared directory portable across EAS CLI VCS
    # checks. This is an isolated payload repository, never the user's branch.
    subprocess.run(["git", "-C", str(destination), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(destination), "-c", "core.hooksPath=/dev/null",
                    "-c", "commit.gpgsign=false", "-c", "user.name=Expo eval harness",
                    "-c", "user.email=evals@localhost", "commit", "-qm", "Prepared evaluator shard"], check=True)
    return spec


def eas(project: Path, *args: str, json_output=True):
    command = [*EAS, *args, "--non-interactive"]
    if json_output:
        command.append("--json")
    result = subprocess.run(command, cwd=project, capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Keep credentials/remote response bodies out of controller reports.
        raise RuntimeError(f"EAS {args[0]} exited {result.returncode}; run that command interactively for diagnostics")
    return json.loads(result.stdout) if json_output else None


def artifact_url(run: dict) -> str | None:
    matches = [a for job in run.get("jobs", []) for a in job.get("artifacts") or []
               if a.get("filename") == "eval-artifacts.tar.gz" or a.get("name") == "simbench-evidence"]
    if len(matches) > 1:
        raise ValueError("Ambiguous simbench artifact")
    return matches[0].get("downloadUrl") if matches else None


def unpack(archive: Path, destination: Path, expected: dict) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        if len(members) > 20000 or sum(m.size for m in members) > MAX_ARCHIVE_BYTES:
            raise ValueError("Artifact exceeds extraction limits")
        names = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Artifact contains an unsafe member")
            if str(path) in names:
                raise ValueError("Artifact contains duplicate paths")
            names.add(str(path))
        manifest = next((m for m in members if PurePosixPath(m.name) == PurePosixPath("manifest.json")), None)
        if manifest is None or not manifest.isfile() or manifest.size > 1024 * 1024:
            raise ValueError("Missing shard manifest")
        source = tf.extractfile(manifest)
        assert source is not None
        if json.load(source) != expected:
            raise ValueError("Artifact belongs to different source or shard")
        destination.mkdir(parents=True)
        tf.extractall(destination, members=members, filter="data")


def collect(project: Path, run_id: str, output: Path, timeout: int) -> dict:
    expected = json.loads((project / "eval-source.json").read_text())
    deadline = time.monotonic() + timeout
    run = {}
    while time.monotonic() < deadline:
        run = eas(project, "workflow:view", run_id)
        if run.get("status") in TERMINAL:
            url = artifact_url(run)
            if url:
                output.mkdir(parents=True, exist_ok=True)
                archive = output / "eval-artifacts.tar.gz"
                if not url.startswith("https://"):
                    raise ValueError("Expected HTTPS artifact URL")
                with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as stream:
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES:
                            raise ValueError("Artifact download exceeds size limit")
                        stream.write(chunk)
                destination = output / "evidence"
                unpack(archive, destination, expected)
                if expected["kind"] == "candidate-eas-shard":
                    from expo_harbor_evals.mobile_scenarios import validate_result
                    worker = json.loads((destination / "native-eval/details.json").read_text())
                    validate_result(worker)
                    summary = {"ok": worker["status"] == "passed" and run["status"] == "SUCCESS",
                               "kind": "native-ui", "status": worker["status"], "checks": worker["checks"]}
                    if worker["task"] != expected["task"]:
                        raise ValueError("Native result task mismatch")
                    prepared = json.loads((project / "candidate/input.json").read_text())
                    if worker["input"] != prepared:
                        raise ValueError("Native result submission mismatch")
                else:
                    summary = check_calibration(destination / "calibration/trials", expected["attempts"], expected["task"] == FLOW_TASK)
                    worker = json.loads((destination / "calibration/calibration.json").read_text())
                    summary["ok"] = summary["ok"] and worker.get("ok") is True and run["status"] == "SUCCESS"
                write_json(output / "summary.json", summary)
                return summary
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    raise TimeoutError(f"Run {run_id}: {run.get('status', 'unknown')}; artifact unavailable before deadline")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--repo", type=Path, default=Path.cwd())
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--project-id", help="EAS project UUID; defaults to EAS_EVAL_PROJECT_ID")
    prep.add_argument("--task", default=FLOW_TASK)
    prep.add_argument("--attempts", type=int, default=1)
    prep.add_argument("--candidate", type=Path, help="Evaluate this submitted codegen workspace on the EAS simulator")
    for name in ("run", "collect", "cancel"):
        sub = commands.add_parser(name)
        sub.add_argument("--project", type=Path, required=True)
        if name != "run":
            sub.add_argument("--run-id", required=True)
        if name != "cancel":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    load_eas_config(Path.cwd())
    if args.command == "prepare":
        args.project_id = args.project_id or os.environ.get("EAS_EVAL_PROJECT_ID")
        if not args.project_id:
            parser.error("Set EAS_EVAL_PROJECT_ID in .env.local or pass --project-id (see .env.example)")
        try:
            uuid.UUID(args.project_id)
        except ValueError:
            parser.error("EAS project ID must be a UUID, not a project name or slug")
        kwargs = {"candidate": args.candidate.resolve()} if args.candidate else {}
        spec = prepare(args.repo.resolve(), args.output.resolve(), args.project_id, args.task, args.attempts, **kwargs)
        print(f"Prepared shard {spec['shard_id']} at {args.output}")
        return
    project = args.project.resolve()
    if args.command == "cancel":
        eas(project, "workflow:cancel", args.run_id, json_output=False)
        return
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    run_id = getattr(args, "run_id", None)
    if args.command == "run":
        args.output.mkdir(parents=True, exist_ok=False)
        write_json(args.output / "run.json", {"status": "submitting", "project": str(project)})
        started = eas(project, "workflow:run", WORKFLOW)
        run_id = started["id"]
        print(f"Started EAS run {run_id}", flush=True)
    try:
        if args.command == "run":
            write_json(args.output / "run.json", {"status": "submitted", "id": run_id,
                       "url": started.get("url"), "project": str(project)})
        summary = collect(project, run_id, args.output, args.timeout)
    except BaseException:
        if args.command == "run":
            try:
                eas(project, "workflow:cancel", run_id, json_output=False)
            except Exception:
                print(f"Automatic cancellation failed; cancel EAS run {run_id} explicitly")
        raise
    print(f"Downloaded evidence: {args.output / 'evidence'}")
    raise SystemExit(0 if summary["ok"] else 1)
