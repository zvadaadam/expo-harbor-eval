"""Calibrate native scenarios against complete references and broken apps.

This command builds real Expo apps and starts disposable simulators. It makes
no model calls. The unchanged app must build and fail a UI assertion; a build
error or missing tool cannot establish the negative control.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from expo_harbor_evals.codegen_calibrate import _copy_environment
from expo_harbor_evals.evaluation_identity import task_digest
from expo_harbor_evals.mobile_eval import PROFILES, ROOT, execute, prepare
from expo_harbor_evals.mobile_scenarios import validate_result
from expo_harbor_evals.simbench_evidence import write_json


def assess_control(condition: str, result: dict) -> bool:
    validate_result(result)
    if condition.startswith("reference"):
        return result["status"] == "passed"
    return (result["status"] == "failed" and not result.get("errors")
            and {"name": "candidate-build", "passed": True} in result.get("checks", [])
            and any(c.get("name") == "native-ui" and c.get("passed") is False
                    for c in result.get("checks", [])))


def calibrate(task: Path, output: Path, attempts: int, timeout: int) -> dict:
    if attempts < 1 or timeout < 1:
        raise ValueError("Attempts and timeout must be positive")
    if task.name not in PROFILES:
        raise ValueError("No native scenario for this task")
    output.mkdir(parents=True, exist_ok=False)
    conditions = ["baseline", "reference"]
    if (task / "solution/reference-alternative").exists():
        conditions.append("reference-alternative")
    # Timer-based modal workarounds are source-contract violations but may
    # succeed at runtime. Do not insist that timing always reproduces a bug.
    if PROFILES[task.name] in ("slider", "picker"):
        conditions.append("distractor")
    rows = []
    for attempt in range(attempts):
        for condition in conditions:
            trial = output / f"{condition}-{attempt + 1}"
            workspace = trial / "candidate"
            workspace.mkdir(parents=True)
            _copy_environment(task / "environment", workspace)
            if condition != "baseline":
                shutil.copytree(task / "solution" / condition, workspace, dirs_exist_ok=True)
            prepared = trial / "evaluation"
            try:
                prepare(task.name, workspace, prepared)
                result = execute(prepared, timeout=timeout)
                ok = assess_control(condition, result)
                row = {"condition": condition, "attempt": attempt + 1,
                       "status": result["status"], "ok": ok, "evidence": str(prepared.relative_to(output))}
            except Exception as exc:
                row = {"condition": condition, "attempt": attempt + 1,
                       "status": "infra-error", "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            summary = {"schema_version": 1, "kind": "native-scenario-calibration",
                "task": task.name, "task_sha256": task_digest(task), "attempts": attempts,
                "complete": len(rows) == len(conditions) * attempts,
                "ok": len(rows) == len(conditions) * attempts and all(r["ok"] for r in rows),
                "results": rows}
            write_json(output / "calibration.json", summary)
            print(f"{condition} #{attempt + 1}: {row['status']} ({'accepted' if row['ok'] else 'calibration failed'})", flush=True)
            # Native build products can be gigabytes. Keep all evidence, locks,
            # source hashes and logs; the original task retains the fixtures.
            for name in ("app", "derived"):
                shutil.rmtree(prepared / name, ignore_errors=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=sorted(PROFILES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=3000, help="Seconds per native trial")
    args = parser.parse_args()
    if args.attempts < 1 or args.timeout < 1:
        parser.error("attempts and timeout must be positive")
    result = calibrate(ROOT / "tasks/codegen" / args.task, args.output.resolve(), args.attempts, args.timeout)
    raise SystemExit(0 if result["ok"] else 1)
