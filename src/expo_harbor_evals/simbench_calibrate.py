"""Run no-op / UI oracle / wrong-order brackets through real Harbor trials."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

from expo_harbor_evals.simbench_evidence import write_json

FLOW_TASK = "simbench-ios-07-goldennotes-shift-flow"


def calibration_config(repo: Path, task: str, attempts: int) -> dict:
    agents = [{"name": "nop"}, {"name": "oracle"}]
    if task == FLOW_TASK:
        agents.append({"name": "oracle", "model_name": "out-of-order",
                       "env": {"SIMBENCH_FLOW_ORDER": "out-of-order"}})
    return {
        "jobs_dir": "runs", "n_attempts": attempts, "n_concurrent_trials": 1,
        "environment": {"import_path": "expo_harbor_evals.simbench_env:SimbenchEnvironment",
                        "delete": True},
        "agents": agents,
        "datasets": [{"path": str(repo / "tasks/simbench"), "task_names": [task]}],
    }


def check_calibration(run: Path, attempts: int, flow: bool) -> dict:
    rows = []
    expected_counts = {"nop": attempts, "oracle": attempts}
    if flow:
        expected_counts["out-of-order"] = attempts
    counts = {key: 0 for key in expected_counts}
    for path in sorted(run.glob("*/result.json")):
        try:
            raw = json.loads(path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("Trial result must be an object")
        except (OSError, ValueError) as exc:
            rows.append({"trial": path.parent.name, "passed": False,
                         "error": f"Invalid trial result: {type(exc).__name__}"})
            continue
        agent = raw.get("agent_info") or {}
        name = (agent.get("model_info") or {}).get("name")
        condition = "out-of-order" if name == "out-of-order" else agent.get("name")
        rewards = (raw.get("verifier_result") or {}).get("rewards") or {}
        expected = 1.0 if condition == "oracle" else 0.0
        passed = (condition in counts and not raw.get("exception_info")
                  and rewards.get("sim_runner_ok") == 1.0
                  and rewards.get("reward") == expected)
        if condition in counts:
            counts[condition] += 1
        if condition == "out-of-order":
            passed = passed and rewards.get("sim_flow_state_complete") == 1.0
        # Harbor's oracle records nonzero exits without necessarily raising.
        oracle_exit = path.parent / "agent/exit-code.txt"
        if oracle_exit.exists() and oracle_exit.read_text().strip() != "0":
            passed = False
        rows.append({"trial": path.parent.name, "condition": condition,
                     "expected": expected, "rewards": rewards, "passed": passed})
    return {"ok": bool(rows) and counts == expected_counts and all(r["passed"] for r in rows),
            "counts": counts, "expected_counts": expected_counts, "trials": rows}


def cleanup_devices(run: Path) -> list[str]:
    """Recover trial-owned devices if Harbor was interrupted before stop()."""
    records = list(run.glob("*/artifacts/device.json"))
    records += list(run.glob("*/artifacts/logs/artifacts/device.json"))
    records += list(run.glob("*/_local_env/logs/artifacts/device.json"))
    if not records:
        return []
    errors = []
    try:
        result = subprocess.run(["xcrun", "simctl", "list", "devices", "-j"],
                                capture_output=True, text=True, check=True, timeout=30)
        devices = {d["udid"]: d for group in json.loads(result.stdout)["devices"].values() for d in group}
        handled = set()
        for path in records:
            record = json.loads(path.read_text())
            device, name = record["device"], record["session"]
            if device in handled or device not in devices:
                continue
            if not re.fullmatch(r"harbor-[a-f0-9]{12}", name) or devices[device]["name"] != name:
                errors.append("Device ownership mismatch; manual cleanup required")
                continue
            handled.add(device)
            subprocess.run(["agent-device", "close", "--session", name],
                           capture_output=True, timeout=30)
            subprocess.run(["xcrun", "simctl", "shutdown", device], capture_output=True, timeout=30)
            subprocess.run(["xcrun", "simctl", "delete", device], capture_output=True, check=True, timeout=30)
    except Exception as exc:
        errors.append(f"Device cleanup failed: {type(exc).__name__}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--task", default=FLOW_TASK)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=2100,
                        help="Whole shard seconds; reserve time for artifact upload")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.attempts < 1 or args.timeout < 1 or Path(args.task).name != args.task:
        parser.error("Invalid task, attempts, or timeout")
    if not (repo / "tasks/simbench" / args.task / "task.toml").is_file():
        parser.error("Task not found")
    output = (args.output or repo / "runs" / f"simbench-calibration-{time.time_ns()}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = calibration_config(repo, args.task, args.attempts)
    config["jobs_dir"] = str(output)
    config_path = output / "job.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    run = output / "trials"
    exit_code = None
    failure = None
    process = None
    try:
        with (output / "harbor.log").open("w") as log:
            process = subprocess.Popen(
                ["harbor", "run", "-c", str(config_path), "--job-name", "trials", "--yes"],
                cwd=repo, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            print(f"Running {args.task}; log: {output / 'harbor.log'}", flush=True)
            exit_code = process.wait(timeout=args.timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        failure = type(exc).__name__
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    finally:
        cleanup_errors = cleanup_devices(run)
        summary = check_calibration(run, args.attempts, args.task == FLOW_TASK)
        summary.update(exit_code=exit_code, failure=failure, cleanup_errors=cleanup_errors)
        summary["ok"] = summary["ok"] and exit_code == 0 and failure is None and not cleanup_errors
        write_json(output / "calibration.json", summary)
    print(f"Calibration {'passed' if summary['ok'] else 'FAILED'}: {output / 'calibration.json'}")
    sys.exit(0 if summary["ok"] else 1)
