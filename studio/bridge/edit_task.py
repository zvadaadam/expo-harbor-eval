"""Edit a library task with conflict detection, rollback and verifier preservation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
from uuid import uuid4

import tomli_w
from catalog import ROOT, contained, editable_files, task_dir, task_record
from export_task import KIT, measurement, validate_plan, grading_plan, rubric_criteria, uses_kit
from expo_harbor_evals.codegen_rewardkit_runner import submission_manifest
from expo_harbor_evals.evaluation_identity import task_digest


def safe_digest(task: Path) -> str:
    for path in task.rglob("*"):
        contained(ROOT, path)
    return task_digest(task)


def load_edit(task_id: str) -> dict:
    task = task_dir(task_id)
    fingerprint = safe_digest(task)
    detail = task_record(task, True)
    native = detail["family"] == "simbench"
    result = {
        "fingerprint": fingerprint, "family": detail["family"],
        "policyCriteria": detail["policyCriteria"],
        "protectedGrading": native or any(m in detail["measurements"] for m in ("policy-behavior", "native-ui")),
        "draft": {
            "id": str(uuid4()), "revision": 0, "title": detail["title"], "slug": task_id,
            "category": detail["category"], "difficulty": detail["difficulty"],
            "motivation": detail["motivation"], "instruction": detail["instruction"],
            "sourceTask": task_id, "criteria": detail["criteria"],
            'scoring': detail['scoring'],
            # Simulator app sources are shared by multiple tasks; edit their brief here.
            "files": [] if native else editable_files(task),
            "mustFail": detail["calibration"].get("distractor", {}).get("must_fail", []),
            "baselineMustFail": detail["calibration"].get("baseline-comment", {}).get("must_fail", []),
            "updatedAt": "",
        },
    }
    if safe_digest(task) != fingerprint:
        raise ValueError("This task changed while loading. Reload the editor.")
    return result


def update_task(task_id: str, fingerprint: str, draft: dict) -> dict:
    state = contained(ROOT, ROOT / ".studio")
    state.mkdir(exist_ok=True, mode=0o700)
    lock = contained(ROOT, state / "execution.lock")
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A local run or edit is active. Save again when it finishes.")
        return _update_locked(task_id, fingerprint, draft, state)


def _update_locked(task_id: str, fingerprint: str, draft: dict, state: Path) -> dict:
    target = task_dir(task_id)
    existing = load_edit(task_id)
    before = existing["draft"]
    if existing["fingerprint"] != fingerprint:
        raise ValueError("This task changed since you opened it. Reload before saving; your edits have not been written.")
    if draft["slug"] != task_id or draft["sourceTask"] != task_id:
        raise ValueError("Editing cannot rename a library task. Duplicate it to create a new task.")
    if not draft["title"].strip() or len(draft["instruction"].strip()) < 40 or not draft["motivation"].strip():
        raise ValueError("Add a title, a task prompt, and the source or reason for this task.")
    native = existing["family"] == "simbench"
    if (draft["category"] == "simbench") != native:
        raise ValueError("A task's family cannot be changed by editing its category.")
    if native and (draft["files"] or draft["criteria"]):
        raise ValueError("Simulator app and verifier changes use the repository CLI.")
    if not native and (not draft["criteria"] or any(not c["description"].strip() for c in draft["criteria"])):
        raise ValueError("Describe every grading check.")
    ids = {c["id"] for c in draft["criteria"]}
    if len(ids) != len(draft["criteria"]):
        raise ValueError("Duplicate check IDs")
    for field in ("mustFail", "baselineMustFail"):
        if not set(draft[field]) <= ids:
            raise ValueError("A calibration example references a removed check.")
    default = {"kind": "ai-review", "config": {}}
    plan = grading_plan(draft)
    if existing["protectedGrading"] and plan["checks"] != {c["id"]: c.get("grading", default) for c in before["criteria"]}:
        raise ValueError("This task has a native or policy verifier. Keep its check IDs and grading methods intact.")
    if existing['protectedGrading']:
        before_scores = [{k: c.get(k) for k in ('type', 'points', 'min', 'max', 'negate', 'optional')} for c in before['criteria']]
        next_scores = [{k: c.get(k) for k in ('type', 'points', 'min', 'max', 'negate', 'optional')} for c in draft['criteria']]
        if before_scores != next_scores or draft.get('scoring', before['scoring']) != before['scoring']:
            raise ValueError('Keep scoring intact for a task with a policy or native verifier')

    config = tomllib.loads((target / "task.toml").read_text())
    config["metadata"].update(title=draft["title"], category=draft["category"], difficulty=draft["difficulty"], motivation=draft["motivation"],
                              reference_validation="Edited in Studio. Re-run calibration for this revision.")
    # Editing a held task does not establish that the missing capability works.
    if not str(config["metadata"].get("validation_status", "")).startswith("held"):
        config["metadata"]["validation_status"] = "requires-calibration"
    suite_path = contained(ROOT, ROOT / "suites/mobile-v2.json")
    suite_bytes = suite_path.read_bytes() if suite_path.exists() else None
    suite = json.loads(suite_bytes) if suite_bytes else None
    with tempfile.TemporaryDirectory(prefix="task-edit-", dir=state) as temporary:
        stage = Path(temporary) / task_id
        # load_edit checked all paths, including hidden assets preserved by the copy.
        shutil.copytree(target, stage)
        def write(relative: str, content: str):
            path = contained(stage, stage / relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        write("instruction.md", draft["instruction"].rstrip() + "\n")
        if not native:
            areas = {"environment": "environment", "reference": "solution/reference", "distractor": "solution/distractor", "checks": "tests/checks"}
            for file in before["files"]:
                contained(stage, stage / areas[file["area"]] / file["path"]).unlink()
            from kit_runner import relative_path
            for file in draft["files"]:
                if not relative_path(file["path"]) or Path(file["path"]).name in {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
                    raise ValueError("Invalid editable file path")
                write(f"{areas[file['area']]}/{file['path']}", file["content"])
            if not any(p.is_file() for p in (stage / "environment").rglob("*.tsx")):
                raise ValueError("Keep a TSX starting file for calibration.")
            if not any(p.is_file() for p in (stage / "solution/reference").rglob("*")):
                raise ValueError("Keep a correct reference solution.")
            rubric_path = stage / "tests/requirements/rubric.toml"
            rubric = tomllib.loads(rubric_path.read_text())
            old = {c.get("id", c["name"]): c for c in rubric["criterion"]}
            catalog = json.loads((KIT / "catalog.json").read_text())
            rubric["criterion"] = [{**old.get(c['id'], {}), **c} for c in rubric_criteria(draft, catalog)]
            if not existing['protectedGrading']:
                rubric['scoring'] = plan['scoring']
            from rewardkit.models import JudgeTomlConfig
            JudgeTomlConfig.model_validate(rubric)
            write("tests/requirements/rubric.toml", tomli_w.dumps(rubric))
            validate_plan(plan, rubric['criterion'], catalog, stage / "tests")
            measured = measurement(plan)
            if not existing["protectedGrading"]:
                source_runner = ROOT / "src/expo_harbor_evals/codegen_rewardkit_runner.py"
                if uses_kit(draft):
                    write("tests/requirements/grading.json", json.dumps(plan, indent=2) + "\n")
                    write("tests/requirements/kit-catalog.json", json.dumps(catalog, indent=2) + "\n")
                    shutil.copyfile(KIT / "kit_runner.py", stage / "tests/run_rewardkit.py")
                    shutil.copyfile(source_runner, stage / "tests/source_runner.py")
                else:
                    shutil.copyfile(source_runner, stage / "tests/run_rewardkit.py")
                    for name in ("requirements/grading.json", "requirements/kit-catalog.json", "source_runner.py"):
                        (stage / "tests" / name).unlink(missing_ok=True)
                config["metadata"].update(verifier="rewardkit-source" if measured == "source-review" else "rewardkit-checks", measurement=measured)
                trajectory = '/logs/agent/trajectory.json'
                config['artifacts'] = [a for a in config.get('artifacts', []) if not isinstance(a, dict) or a.get('source') != trajectory]
                if any(c['kind'].startswith('trajectory-') for c in plan['checks'].values()):
                    config['artifacts'].append({'source': trajectory, 'destination': 'agent-trajectory.json'})
            config["metadata"]["requirements"] = len(draft["criteria"])
            write("tests/requirements/baseline-manifest.json", json.dumps({"schema": 1, "files": submission_manifest(stage / "environment")}, indent=2) + "\n")
            calibration_path = stage / "tests/requirements/calibration.json"
            calibration = json.loads(calibration_path.read_text()) if calibration_path.exists() else {"schema_version": 1}
            for bracket, field in (("baseline-comment", "baselineMustFail"), ("distractor", "mustFail")):
                if draft[field] or bracket in calibration:
                    calibration[bracket] = {**calibration.get(bracket, {}), "must_fail": draft[field]}
            write("tests/requirements/calibration.json", json.dumps(calibration, indent=2) + "\n")
            shutil.rmtree(stage / "tests/reference")
            shutil.copytree(stage / "solution/reference", stage / "tests/reference")
        write("task.toml", tomli_w.dumps(config))
        from harbor.models.task.config import TaskConfig
        TaskConfig.model_validate(config)
        if safe_digest(target) != fingerprint or (suite_path.read_bytes() if suite_path.exists() else None) != suite_bytes:
            raise ValueError("The task changed while saving. Reload before retrying.")
        if suite is not None and task_id in suite["tasks"]:
            suite = deepcopy(suite)
            suite["tasks"][task_id]["definition_sha256"] = task_digest(stage)
        backup = Path(temporary) / "original"
        suite_temp = None
        if suite is not None:
            suite_temp = contained(ROOT, suite_path.with_name(f".{suite_path.name}.{uuid4()}.tmp"))
            suite_temp.write_text(json.dumps(suite, indent=2, sort_keys=True) + "\n")
        try:
            target.rename(backup)
            try:
                stage.rename(target)
                if suite_temp:
                    suite_temp.replace(suite_path)
            except BaseException:
                if target.exists():
                    shutil.rmtree(target)
                backup.rename(target)
                if suite_bytes is not None:
                    suite_path.write_bytes(suite_bytes)
                raise
        finally:
            if suite_temp:
                suite_temp.unlink(missing_ok=True)
    result = load_edit(task_id)
    result["draft"].update(id=draft["id"], revision=draft["revision"] + 1, updatedAt=datetime.now(timezone.utc).isoformat())
    return result
