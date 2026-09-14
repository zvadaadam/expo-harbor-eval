"""Versioned suite membership and non-secret experiment identity."""

import argparse
import hashlib
import json
import os
import tomllib
from pathlib import Path

from harbor.utils.env import resolve_env_vars

from expo_harbor_evals.simbench_evidence import write_json


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def task_digest(task: Path) -> str:
    files = {}
    for path in sorted(task.rglob("*")):
        relative = path.relative_to(task)
        if any(p in ("__pycache__", ".git", ".DS_Store") for p in relative.parts):
            continue
        if path.is_file():
            files[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(files)


def make_suite(repo: Path) -> dict:
    tasks = {}
    for config in sorted((repo / "tasks").rglob("task.toml")):
        meta = tomllib.loads(config.read_text())["metadata"]
        tasks[config.parent.name] = {"path": str(config.parent.relative_to(repo)),
            "family": meta["family"], "definition_sha256": task_digest(config.parent)}
    presentation = {"report.py", "report_view.py", "viewer.py", "export.py", "catalog.py"}
    engine_paths = [p for p in (repo / "src/expo_harbor_evals").glob("*.py") if p.name not in presentation]
    engine_paths += [p for p in (repo / "mobile/templates").rglob("*") if p.is_file()]
    engine_paths += [repo / name for name in ("pyproject.toml", "uv.lock") if (repo / name).exists()]
    engine = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(engine_paths)}
    return {"schema_version": 1, "suite": "expo-mobile-v2", "tasks": tasks, "engine": engine}


def trial_identity(task: Path, config: dict, job: dict | None = None) -> dict:
    """Use a common suite digest, plus the actual condition (not a display alias)."""
    repo = next((p for p in task.parents if (p / "suites/mobile-v2.json").exists()), None)
    if repo is None:
        return {"measurement": "unversioned", "task_sha256": task_digest(task)}
    suite = json.loads((repo / "suites/mobile-v2.json").read_text())
    record = suite["tasks"].get(task.name)
    if not record or record["definition_sha256"] != task_digest(task):
        raise ValueError("Task changed since suite lock; review and run expo-eval-suite lock")
    for filename, expected in suite["engine"].items():
        if hashlib.sha256((repo / filename).read_bytes()).hexdigest() != expected:
            raise ValueError("Evaluator changed since suite lock; review and run expo-eval-suite lock")
    agent = config.get("agent", {})
    verifier = config.get("verifier", {}).get("env", {})
    condition = {"agent": {k: agent.get(k) for k in ("name", "import_path", "model_name", "skills")},
                 "kwargs": {k: agent.get("kwargs", {}).get(k) for k in ("preface", "allowed_tools", "allow_shell", "reasoning_effort", "clean_config")},
                 "verifier": resolve_env_vars({k: verifier[k] for k in ("EXPO_EVAL_VERIFIER_MODE", "REWARDKIT_JUDGE", "REWARDKIT_MODEL", "REWARDKIT_REASONING_EFFORT") if k in verifier})}
    condition["runtime_requested"] = os.environ.get("SIMBENCH_RUNTIME")
    condition["cohort"] = [{"dataset": Path(d.get("path", "")).name,
                            "tasks": sorted(d.get("task_names") or [])}
                           for d in (job or {}).get("datasets", [])]
    condition["task_paths"] = sorted(Path(t.get("path", "")).name for t in (job or {}).get("tasks", []))
    condition["budget"] = {k: config.get(k) for k in (
        "timeout_multiplier", "agent_timeout_multiplier", "verifier_timeout_multiplier")}
    condition["agent_timeout"] = agent.get("override_timeout_sec")
    measurement = {"expo-codegen": "source-review", "simbench": "device-use"}[record["family"]]
    if condition["verifier"].get("EXPO_EVAL_VERIFIER_MODE") == "reference":
        measurement = "reference-smoke"
    elif condition["verifier"].get("EXPO_EVAL_VERIFIER_MODE") == "mobile":
        measurement = "native-ui"
    return {"suite": suite["suite"], "suite_sha256": fingerprint(suite),
            "experiment_sha256": fingerprint({"suite": suite, "condition": condition}),
            "task_sha256": record["definition_sha256"], "measurement": measurement,
            "condition": condition}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("lock", "check"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    path = args.repo / "suites/mobile-v2.json"
    current = make_suite(args.repo)
    if args.command == "lock":
        write_json(path, current)
        print(f"Locked {len(current['tasks'])} tasks: {path}")
    elif not path.exists() or json.loads(path.read_text()) != current:
        parser.exit(1, "Suite definitions changed; review and update the suite lock.\n")
    else:
        print("Suite definitions match the lock")
