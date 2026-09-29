"""Export a reviewable Harbor task; never modify tasks/ or the suite lock."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import sys
import tomli_w

from catalog import ROOT, contained
from expo_harbor_evals.codegen_scaffold import DOCKERFILE, VERIFIER_DOCKERFILE, TEST_SH, SOLUTION_SH, JUDGE_PROMPT

KIT = Path(__file__).resolve().parents[2] / "graders"
sys.path.insert(0, str(KIT))
from kit_runner import measurement, validate_plan


def grading_plan(draft: dict) -> dict:
    return {"schemaVersion": 1, "scoring": draft.get('scoring', {'aggregation': 'weighted-mean', 'threshold': 0.5}),
            "checks": {c["id"]: c.get("grading", {"kind": "ai-review", "config": {}}) for c in draft["criteria"]}}


def rubric_criteria(draft: dict, catalog: dict) -> list[dict]:
    result = []
    for criterion in draft['criteria']:
        row = {key: criterion[key] for key in ('id', 'name', 'description', 'weight', 'type', 'points', 'min', 'max', 'negate', 'optional') if key in criterion}
        kind = criterion.get('grading', {}).get('kind', 'ai-review')
        if kind != 'ai-review':
            row.update(type='numeric' if catalog['checks'][kind].get('score') == 'continuous' else 'binary', min=0, max=1)
        row.setdefault('type', 'binary')
        result.append(row)
    return result


def uses_kit(draft: dict) -> bool:
    return measurement(grading_plan(draft)) != 'source-review' or draft.get('scoring', {}).get('aggregation', 'weighted-mean') != 'weighted-mean' or any(
        c.get('type', 'binary') != 'binary' or c.get('negate') or c.get('optional') for c in draft['criteria'])


def export_task(draft: dict) -> dict:
    if draft['category'] == 'simbench':
        from simulator_task import export_simulator
        return export_simulator(draft, ROOT)
    catalog = json.loads((KIT / "catalog.json").read_text())
    plan = grading_plan(draft)
    validate_plan(plan, draft["criteria"], catalog)
    measured = measurement(plan)
    has_programmatic = uses_kit(draft)
    slug = draft["slug"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Invalid task ID")
    if not re.fullmatch(r"[a-f0-9-]{36}", draft["id"]):
        raise ValueError("Invalid draft ID")
    revision = int(draft["revision"])
    parent = contained(ROOT, ROOT / "outputs/studio" / draft["id"] / str(revision))
    target = parent / slug
    if target.exists():
        raise ValueError("This revision is already exported. Save a new revision to export changes.")
    parent.mkdir(parents=True, exist_ok=True)
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    with tempfile.TemporaryDirectory(prefix=".export-", dir=parent) as temp:
        stage = Path(temp) / slug
        stage.mkdir()
        def write(relative, content):
            path = contained(stage, stage / relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        for file in draft["files"]:
            area = {"environment": "environment", "reference": "solution/reference", "distractor": "solution/distractor", "checks": "tests/checks"}[file["area"]]
            path = file["path"]
            if any(p.startswith('.') for p in Path(path).parts) or '\\' in path:
                raise ValueError("Invalid draft file path")
            write(f"{area}/{path}", file["content"])
        write("instruction.md", draft["instruction"] + "\n")
        write("task.toml", f'''schema_version = "1.3"
artifacts = [{{ source = "/app", destination = "app", exclude = ["node_modules", ".git", ".expo", ".env", ".env.*", ".npmrc", ".netrc", "__pycache__", "Dockerfile"] }}]

[task]
name = {quote("expo-harbor/" + slug)}
description = {quote(draft["title"])}
authors = [{{ name = "Local task author" }}]

[metadata]
family = "expo-codegen"
title = {quote(draft["title"])}
category = {quote(draft["category"])}
tier = "code-gen"
difficulty = {quote(draft["difficulty"])}
motivation = {quote(draft["motivation"])}
requirements = {len(draft["criteria"])}
verifier = {quote('rewardkit-checks' if has_programmatic else 'rewardkit-source')}
measurement = {quote(measured)}
validation_status = {quote('requires-grader-calibration' if has_programmatic else 'requires-judge-calibration')}
reference_validation = "Exported from Studio. Controls have not been run."

[agent]
timeout_sec = 900.0
[verifier]
environment_mode = "separate"
timeout_sec = 900.0
[environment]
network_mode = "public"
build_timeout_sec = 600.0
workdir = "/app"
cpus = 2
memory_mb = 4096
storage_mb = 10240
''')
        rubric = {'judge': {'judge': 'anthropic/claude-sonnet-4-6', 'files': ['/app'], 'prompt_template': 'judge-prompt.md', 'timeout': 300, 'reasoning_effort': 'medium'},
                  'criterion': rubric_criteria(draft, catalog), 'scoring': plan['scoring']}
        write("tests/requirements/rubric.toml", tomli_w.dumps(rubric))
        prompt = JUDGE_PROMPT if not has_programmatic else JUDGE_PROMPT.replace('Decide pass or fail for every criterion', 'Use each criterion’s declared binary, Likert, or numeric scale')
        write("tests/requirements/judge-prompt.md", prompt)
        if any(c['kind'].startswith('trajectory-') for c in plan['checks'].values()):
            config_path = stage / 'task.toml'
            config = __import__('tomllib').loads(config_path.read_text())
            config['artifacts'].append({'source': '/logs/agent/trajectory.json', 'destination': 'agent-trajectory.json'})
            config_path.write_text(tomli_w.dumps(config))
        if has_programmatic:
            write("tests/requirements/grading.json", json.dumps(plan, indent=2) + "\n")
            write("tests/requirements/kit-catalog.json", json.dumps(catalog, indent=2) + "\n")
            validate_plan(plan, draft["criteria"], catalog, stage / "tests")
        write("tests/requirements/calibration.json", json.dumps({"schema_version": 1, "baseline-comment": {"must_fail": draft["baselineMustFail"]}, "distractor": {"must_fail": draft["mustFail"]}}, indent=2) + "\n")
        # Match the canonical submission manifest (vendored node_modules is
        # available to the agent, but is excluded from the source guard).
        baseline = {str(p.relative_to(stage / "environment")): hashlib.sha256(p.read_bytes()).hexdigest() for p in (stage / "environment").rglob("*") if p.is_file() and not any(part in {"node_modules", "__pycache__"} for part in p.relative_to(stage / "environment").parts)}
        write("tests/requirements/baseline-manifest.json", json.dumps({"schema": 1, "files": baseline}, indent=2) + "\n")
        write("environment/Dockerfile", DOCKERFILE)
        write("tests/Dockerfile", VERIFIER_DOCKERFILE)
        write("tests/test.sh", TEST_SH)
        write("solution/solve.sh", SOLUTION_SH)
        shutil.copytree(stage / "solution/reference", stage / "tests/reference")
        for src, dest in [("codegen_rewardkit_runner.py", "run_rewardkit.py"), ("codegen_reference_check.py", "reference_check.py")]:
            shutil.copyfile(ROOT / "src/expo_harbor_evals" / src, stage / "tests" / dest)
        if has_programmatic:
            (stage / "tests/run_rewardkit.py").rename(stage / "tests/source_runner.py")
            shutil.copyfile(KIT / "kit_runner.py", stage / "tests/run_rewardkit.py")
        for path in [stage / "tests/test.sh", stage / "solution/solve.sh"]:
            path.chmod(0o755)
        # Atomic no-overwrite: mkdir the final target, then move the staged files.
        target.mkdir()
        try:
            for child in stage.iterdir():
                child.rename(target / child.name)
        except Exception:
            shutil.rmtree(target)
            raise
    return {"path": str(target.relative_to(ROOT)), "files": sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file())}
