"""JSON adapter for the studio. Uses the existing reader, never scores a trial."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from expo_harbor_evals import report

_read_json = report.read_json

SKIP = {".git", ".sources", "__pycache__", ".expo", ".DS_Store"}
AREAS = {"environment": "environment", "reference": "solution/reference", "distractor": "solution/distractor", "checks": "tests"}


def contained(root: Path, path: Path) -> Path:
    """Reject symlinks, including ones pointing back inside the allowed root."""
    path = path.absolute()
    root = root.absolute()
    if not path.is_relative_to(root) or ".." in path.parts:
        raise ValueError("Path is outside the allowed directory")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Symlinked paths are not supported")
        if part == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path is outside the allowed directory")
    return path


def read_json(path: Path):
    return _read_json(contained(ROOT, path))


def load_runs(paths: list[Path]):
    # The canonical reader owns normalization, while this adapter owns the
    # filesystem boundary. Each bridge request has its own Python process;
    # scope the replacement to this call so every nested JSON read is checked.
    previous = report.read_json
    report.read_json = read_json
    try:
        return report.load_runs([contained(ROOT, path) for path in paths])
    finally:
        report.read_json = previous


def task_dir(task_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", task_id):
        raise ValueError("Invalid task ID")
    for family in ("codegen", "simbench"):
        path = contained(ROOT, ROOT / "tasks" / family / task_id)
        if (path / "task.toml").is_file():
            return path
    raise ValueError("Task not found")


def files(root: Path):
    if not root.exists():
        return
    contained(ROOT, root)
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.') and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if name.startswith('.') or path.is_symlink():
                continue
            yield contained(root, path)


def file_content(root: Path, relative: str) -> dict:
    if not relative or any(p.startswith('.') for p in Path(relative).parts):
        raise ValueError("Hidden files are not available")
    path = contained(ROOT, contained(root, root / relative))
    if not path.is_file():
        raise ValueError("File not found")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        if path.stat().st_size > 5_000_000:
            raise ValueError("Image exceeds the 5 MB preview limit")
        mime = "jpeg" if path.suffix in {".jpg", ".jpeg"} else path.suffix[1:]
        return {"kind": "image", "content": f"data:image/{mime};base64," + base64.b64encode(path.read_bytes()).decode(), "truncated": False}
    with path.open("rb") as f:
        raw = f.read(200_001)
    if b"\0" in raw:
        raise ValueError("This binary file cannot be previewed")
    return {"kind": "text", "content": raw[:200_000].decode("utf-8", errors="replace"), "truncated": len(raw) > 200_000}


def task_record(path: Path, detail=False) -> dict:
    config = tomllib.loads(contained(ROOT, path / "task.toml").read_text())
    meta = config.get("metadata", {})
    requirements = path / "tests/requirements"
    rubric_path = requirements / "rubric.toml"
    rubric = tomllib.loads(contained(ROOT, rubric_path).read_text()) if rubric_path.exists() else {}
    criteria = [{**{k: c[k] for k in ('type', 'points', 'min', 'max', 'negate', 'optional') if k in c}, "id": c.get("id", c["name"]), "name": c["name"], "description": c.get("description", ""), "weight": c.get("weight", 1)} for c in rubric.get("criterion", [])]
    grading = read_json(requirements / "grading.json")
    if grading:
        for criterion in criteria:
            criterion["grading"] = grading["checks"][criterion["id"]]
    family = meta.get("family", "unknown")
    measurements = ["device-use"] if family == "simbench" else ["source-review"]
    if (requirements / "behavior.json").is_file():
        measurements = ["source-and-policy", "policy-behavior"]
    if (requirements / "runtime.json").is_file():
        measurements.append("native-ui")
    if grading:
        kinds = {check["kind"] for check in grading["checks"].values()}
        measurements = ["source-review" if kinds == {"ai-review"} else "source-and-checks" if "ai-review" in kinds else "programmatic-checks"]
    # Keep filenames/IDs canonical, but use a readable library heading.
    short = re.sub(r"^(feedback|router|sdk|ui|simbench-ios)-\d+-", "", path.name)
    title = meta.get("title") or short.replace("-", " ").capitalize()
    for old, new in [("Oauth", "OAuth"), ("Ios", "iOS"), ("Sdk", "SDK"), ("Api", "API")]:
        title = title.replace(old, new)
    record = {"id": path.name, "title": title, "description": config.get("task", {}).get("description", ""),
              "family": family, "category": meta.get("category", "unknown"), "tier": meta.get("tier", ""),
              "difficulty": meta.get("difficulty", "unknown"), "motivation": meta.get("motivation", ""),
              "validation": meta.get("validation_status", "unknown"), "validationNote": meta.get("reference_validation", ""),
              "held": str(meta.get("validation_status", "")).startswith("held"), "measurements": measurements,
              "checks": len(criteria), "hasReference": (path / "solution/reference").is_dir() or (path / "solution/solve.sh").is_file(),
              "hasDistractor": (path / "solution/distractor").is_dir(), "path": str(path.relative_to(ROOT))}
    if detail:
        record.update(instruction=contained(ROOT, path / "instruction.md").read_text(), criteria=criteria,
                      scoring={'threshold': 0.5, **rubric.get('scoring', {}), 'aggregation': rubric.get('scoring', {}).get('aggregation', 'weighted-mean').replace('_', '-')},
                      policyCriteria=(read_json(requirements / "behavior.json") or {}).get("criteria", []),
                      calibration=read_json(requirements / "calibration.json") or {},
                      files=[{"area": area, "path": str(f.relative_to(path / sub)), "bytes": f.stat().st_size}
                             for area, sub in AREAS.items() for f in files(path / sub)])
    return record


def catalog() -> dict:
    tasks, warnings = [], []
    for config in sorted((ROOT / "tasks").glob("*/*/task.toml")):
        try:
            tasks.append(task_record(config.parent))
        except (ValueError, OSError, KeyError) as exc:
            warnings.append(f"Could not load {config.parent.name}: {exc}")
    return {"tasks": tasks, "warnings": warnings}


def editable_files(path: Path) -> list[dict]:
    result = []
    for area, sub in AREAS.items():
        if area == "checks":
            if not (path / "tests/requirements/grading.json").is_file():
                continue
            sub = "tests/checks"
        for file in files(path / sub):
            if file.name in {"Dockerfile", "docker-compose.yaml", "docker-compose.yml"}:
                continue
            content = file_content(path / sub, str(file.relative_to(path / sub)))
            if content["kind"] != "text" or content["truncated"]:
                raise ValueError("This task has files the text editor cannot safely load.")
            result.append({"area": area, "path": str(file.relative_to(path / sub)), "content": content["content"]})
    return result


def trial_id(path: Path) -> str:
    return hashlib.sha256(str(path.relative_to(ROOT / "runs")).encode()).hexdigest()[:24]


def all_trials():
    trials, warnings = [], []
    runs = ROOT / "runs"
    try:
        contained(ROOT, runs)
    except ValueError as exc:
        return [], [f"Could not read runs: {exc}"]
    if not runs.exists():
        return trials, warnings
    # A run is a directory containing trial directories. Skip artifacts and the
    # archived source submissions used by regrade (they are not new attempts).
    roots = set()
    for directory, dirs, names in os.walk(runs, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {"artifacts", "environment", "agent", "verifier", "node_modules"} and not (Path(directory) / d).is_symlink()]
        path = Path(directory)
        try:
            calibration = read_json(path / "calibration.json") if "calibration.json" in names else None
            if isinstance(calibration, dict) and calibration.get("kind") == "native-scenario-calibration":
                # Loading each evaluation directory separately loses the
                # calibration context and turns controls into model attempts.
                roots.add(path)
                dirs[:] = []
                continue
            if "result.json" in names or "config.json" in names:
                raw = read_json(path / ("result.json" if "result.json" in names else "config.json"))
                if isinstance(raw, dict) and any(k in raw for k in ("task_name", "task", "agent_info", "verifier_result")):
                    roots.add(path.parent)
                    dirs[:] = []
            if "details.json" in names:
                raw = read_json(path / "details.json")
                if isinstance(raw, dict) and raw.get("kind") == "native-ui":
                    roots.add(path)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            warnings.append(f"Could not read {path.name}: {exc}")
            dirs[:] = []
    for root in sorted(roots):
        try:
            _, loaded = load_runs([contained(ROOT, root)])
            trials.extend(t for t in loaded if t.source_dir and not t.source_dir.is_symlink())
        except (ValueError, OSError, KeyError, TypeError) as exc:
            warnings.append(f"Could not read {root.name}: {exc}")
    unique = {str(t.source_dir): t for t in trials}
    return list(unique.values()), warnings


def normal_check(c: dict) -> dict:
    passed = c.get("passed", c.get("pass", c.get("value")))
    if passed is None and isinstance(c.get("score"), (float, int)):
        passed = c["score"] == 1
    return {"name": str(c.get("name") or c.get("id") or c.get("criterion") or "Check"),
            "passed": bool(passed) if passed is not None else None,
            "detail": str(c.get("reason") or c.get("reasoning") or c.get("detail") or c.get("error") or c.get("description") or "No explanation recorded.")}


def trial_record(trial) -> dict:
    raw = read_json(contained(ROOT, trial.source_dir / "result.json")) or {}
    return {"id": trial_id(trial.source_dir), "name": trial.name, "task": trial.task,
            "run": str(trial.source_dir.parent.relative_to(ROOT / "runs")),
            "agent": trial.agent, "model": trial.model, "reward": trial.reward, "outcome": trial.outcome,
            "error": trial.error, "measurement": trial.measurement or "unversioned", "backend": trial.backend or "unknown",
            "cost": trial.cost_usd, "inputTokens": trial.input_tokens, "outputTokens": trial.output_tokens,
            "regradeOf": trial.regrade_of, "startedAt": raw.get("started_at") or "", "finishedAt": raw.get("finished_at") or "",
            "checks": [normal_check(c) for c in (trial.checks or trial.criteria)], "provenance": trial.provenance}


def artifact_paths(trial):
    directories = ("verifier", "agent")
    if trial.measurement == "native-ui":
        directories += ("screens", "logs")
    for sub in directories:
        for path in files(trial.source_dir / sub):
            if path.suffix.lower() in {".json", ".jsonl", ".txt", ".log", ".md", ".png", ".jpg", ".jpeg", ".webp"}:
                yield path
    for name in ("evaluation.json", "result.json", "details.json", "input.json", "reward.json", "failure.png"):
        path = trial.source_dir / name
        if path.is_file() and not path.is_symlink():
            yield path


def main():
    request = json.load(sys.stdin)
    action = request["action"]
    if action == "catalog":
        value = catalog()
    elif action == 'simulator-template':
        from simulator_task import template_snapshot
        value = template_snapshot(request['task'])
    elif action in {"task", "task-file", "duplicate"}:
        path = task_dir(request["task"])
        if action == "task":
            value = task_record(path, True)
        elif action == "task-file":
            value = file_content(path / AREAS[request["area"]], request["path"])
        else:
            record = task_record(path, True)
            if record['family'] == 'simbench':
                from simulator_task import template_snapshot
                value = template_snapshot(request['task'])
            else:
                value = {"task": record, "files": editable_files(path)}
    elif action in {"edit-task", "update-task"}:
        from edit_task import load_edit, update_task
        value = load_edit(request["task"]) if action == "edit-task" else update_task(request["task"], request["fingerprint"], request["draft"])
    elif action in {"runs", "trial", "artifact"}:
        trials, warnings = all_trials()
        if action == "runs":
            value = {"trials": sorted([trial_record(t) for t in trials], key=lambda t: t["startedAt"], reverse=True), "warnings": warnings}
        else:
            trial = next((t for t in trials if trial_id(t.source_dir) == request["id"]), None)
            if trial is None:
                raise ValueError("Attempt not found")
            artifacts = list(artifact_paths(trial))
            if action == "artifact":
                if request["path"] not in {str(p.relative_to(trial.source_dir)) for p in artifacts}:
                    raise ValueError("Artifact not available for this attempt")
                value = file_content(trial.source_dir, request["path"])
            else:
                value = {**trial_record(trial), "artifacts": [{"path": str(p.relative_to(trial.source_dir)), "bytes": p.stat().st_size} for p in artifacts]}
    elif action == "export":
        from export_task import export_task
        value = export_task(request["draft"])
    else:
        raise ValueError("Unknown read action")
    json.dump(value, sys.stdout, allow_nan=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
