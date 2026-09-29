# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "harbor-rewardkit @ git+https://github.com/harbor-framework/harbor.git@cfc54c995e90cd438deb862189a58053b9d89fd3#subdirectory=packages/rewardkit",
#   "tomli-w>=1.2.0",
#   "pillow>=10.0",
#   "openpyxl>=3.1.5",
# ]
# ///
"""Repo-owned recipes over upstream RewardKit. Copied into exported tasks.

The unchanged source runner supplies guards, file discovery and judge overrides.
RewardKit evaluates each check and combines scores; this adapter preserves the
flat, named evidence expected by the existing calibration and report readers.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import importlib.util
import math
import os
import re
from pathlib import Path
import shlex
import shutil
import tempfile
import tomllib
from urllib.parse import urlparse


def relative_path(value: str) -> bool:
    return bool(value) and not any(c in value for c in ('\\', '\0')) and all(
        part and part != '..' and not part.startswith('.') for part in value.split('/')
    )


def json_value(value: str):
    def invalid(value):
        raise ValueError(f"Invalid JSON number: {value}")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            invalid(value)
        return number
    return json.loads(value, parse_constant=invalid, parse_float=finite_float)


def field_value(field: dict, config: dict):
    value = config.get(field['key'], field.get('default', ''))
    if not isinstance(value, str) or len(value) > 8000:
        raise ValueError(f"Invalid {field['label']}")
    if not value.strip() and not field.get('allowEmpty'):
        if field.get('optional'):
            return None
        raise ValueError(f"{field['label']} is required")
    kind = field['type']
    if kind in {'path', 'script', 'python'} and not relative_path(value):
        raise ValueError(f"Invalid relative path: {field['label']}")
    if kind == 'trajectory' and value != '/logs/agent/trajectory.json' and not relative_path(value):
        raise ValueError('Use /logs/agent/trajectory.json or a relative Test files path')
    if kind in {'json', 'column'}:
        value = json_value(value)
        if kind == 'column' and not (isinstance(value, str) and value or type(value) is int and value >= 0):
            raise ValueError('CSV column must be a non-negative integer or a quoted heading')
    if kind in {'integer', 'number'}:
        value = float(value)
        if not math.isfinite(value) or kind == 'integer' and not value.is_integer():
            raise ValueError(f"Invalid number: {field['label']}")
        if value < field.get('min', -math.inf) or value > field.get('max', math.inf):
            raise ValueError(f"Out of range: {field['label']}")
        if kind == 'integer':
            value = int(value)
    if kind == 'regex':
        re.compile(value)
    if kind == 'identifier' and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('Use a Python function name')
    if kind == 'url' and (urlparse(value).scheme not in {'http', 'https'} or not urlparse(value).hostname):
        raise ValueError('Use an http:// or https:// URL')
    return value


def scoring_config(plan: dict) -> dict:
    return {'aggregation': 'weighted-mean', 'threshold': 0.5, **plan.get('scoring', {})}


def validate_plan(plan: dict, definitions: list[dict], catalog: dict, tests: Path | None = None) -> None:
    if plan.get("schemaVersion") != 1 or catalog.get("schemaVersion") != 1:
        raise ValueError("Unsupported grading catalog version")
    checks = plan.get("checks", {})
    ids = [c["id"] for c in definitions]
    if not ids or len(set(ids)) != len(ids) or set(checks) != set(ids):
        raise ValueError("The grading plan must cover every criterion exactly once")
    scoring = scoring_config(plan)
    if scoring['aggregation'] not in {'weighted-mean', 'weighted-sum', 'all-pass', 'any-pass', 'threshold', 'required-pass'}:
        raise ValueError('Unknown aggregation')
    if not isinstance(scoring['threshold'], (float, int)) or not 0 <= scoring['threshold'] <= 1:
        raise ValueError('Threshold must be between 0 and 1')
    for definition in definitions:
        weight = definition.get('weight', 1)
        if not isinstance(weight, (int, float)) or not math.isfinite(weight) or abs(weight) > 100 or (weight < 0 and scoring['aggregation'] != 'weighted-sum'):
            raise ValueError('Negative weights require weighted sum; weights must be finite and between -100 and 100')
        if definition.get('type') == 'numeric' and definition.get('max', 1) <= definition.get('min', 0):
            raise ValueError('Numeric score maximum must exceed its minimum')
    if scoring['aggregation'] == 'required-pass' and all(c.get('optional') for c in definitions):
        raise ValueError('At least one check must be required')
    if scoring['aggregation'] in {'weighted-mean', 'weighted-sum', 'threshold'} and not any(c.get('weight', 1) != 0 for c in definitions):
        raise ValueError('At least one check must have a nonzero weight')
    for key, check in checks.items():
        recipe = catalog["checks"].get(check.get("kind"))
        if recipe is None:
            raise ValueError(f"Unknown grader for {key}")
        config = check.get("config", {})
        fields = recipe["fields"]
        if set(config) - {field["key"] for field in fields}:
            raise ValueError(f"Unknown grader settings for {key}")
        for field in fields:
            value = field_value(field, config)
            if field["type"] in {"script", "python"}:
                if Path(value).suffix not in ({".py"} if field['type'] == 'python' else {".cjs", ".py"}):
                    raise ValueError("Test files must use .cjs or .py")
                if tests is not None:
                    script = tests / "checks" / value
                    if not script.resolve().is_relative_to((tests / "checks").resolve()) or not script.is_file():
                        raise ValueError(f"Missing trusted test file: {value}")


def measurement(plan: dict) -> str:
    kinds = {c["kind"] for c in plan["checks"].values()}
    if kinds == {"ai-review"}:
        return "source-review"
    return "source-and-checks" if "ai-review" in kinds else "programmatic-checks"


@contextmanager
def test_environment():
    """Model credentials and interpreter hooks are not test-script inputs."""
    original = dict(os.environ)
    os.environ.clear()
    os.environ["PATH"] = original.get("PATH", os.defpath)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def programmatic_scores(definitions: list[dict], plan: dict, catalog: dict, workspace: Path, tests: Path):
    from rewardkit import Reward, criteria
    from rewardkit.session import Session, current, set_current, _factory_registry

    functions, weights = [], []
    previous = current()
    factories = dict(_factory_registry)
    set_current(Session())
    try:
        for definition in definitions:
            check = plan["checks"][definition["id"]]
            recipe = catalog["checks"][check["kind"]]
            builtin = recipe['builtin']
            if check['kind'] == 'ai-review':
                continue
            config = {}
            for field in recipe['fields']:
                value = field_value(field, check['config'])
                # JSON null is an expected value, not an omitted optional setting.
                if value is not None or field['type'] == 'json':
                    config[field['key']] = value
            for field in recipe['fields']:
                value = config.get(field['key'])
                if field['type'] == 'path' and value and not (workspace / value).resolve().is_relative_to(workspace):
                    raise ValueError("Check path escapes the submitted workspace")
                if field['type'] == 'trajectory' and value:
                    if value == '/logs/agent/trajectory.json':
                        target = Path(os.environ.get('HARBOR_LOGS_DIR', '/logs')) / 'agent/trajectory.json'
                    else:
                        target = (tests / 'checks' / value).resolve()
                        if not target.is_relative_to((tests / 'checks').resolve()):
                            raise ValueError('Trajectory fixture escapes Test files')
                    config[field['key']] = str(target)
            if check["kind"] == "test-script":
                script = tests / "checks" / config["script"]
                executable = shutil.which("node" if script.suffix == ".cjs" else "python3")
                if executable is None:
                    raise RuntimeError(f"Runtime missing for {script.name}")
                config = {"cmd": shlex.join([executable, str(script), str(workspace)]), "timeout": 30}
            if check['kind'] == 'custom-python':
                spec = importlib.util.spec_from_file_location(f"studio_check_{definition['id']}", tests / 'checks' / config['script'])
                module = importlib.util.module_from_spec(spec)
                with test_environment():
                    spec.loader.exec_module(module)
                    if config['factory'] not in vars(module):
                        raise ValueError('Custom criterion factory not found in its Python file')
                    function = getattr(criteria, config['factory'])(name=definition['id'])
            else:
                function = factories[builtin](**config, name=definition["id"])
            functions.append(function)
            weights.append(definition["weight"])
    finally:
        set_current(previous)
        _factory_registry.clear()
        _factory_registry.update(factories)
    if not functions:
        return []
    with test_environment():
        return Reward(criteria=functions, weights=weights, workspace=workspace,
                      aggregation=scoring_config(plan)['aggregation']).run()


def run_grading(rubric: Path, workspace: Path, output: Path) -> dict:
    import tomli_w
    from rewardkit.models import JudgeTomlConfig, Score
    from rewardkit.reward import aggregate_scores
    from rewardkit.runner import run
    from source_runner import guard_reason, prepare_rubric, reject_judge_errors, submission_manifest, write_guard_result

    rubric, workspace, output = rubric.resolve(), workspace.resolve(), output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    details_path = output.parent / "reward-details.json"
    details_path.unlink(missing_ok=True)
    config = tomllib.loads((rubric / "rubric.toml").read_text())
    JudgeTomlConfig.model_validate(config)
    definitions = config["criterion"]
    plan = json.loads((rubric / "grading.json").read_text())
    catalog = json.loads((rubric / "kit-catalog.json").read_text())
    validate_plan(plan, definitions, catalog, rubric.parent)
    manifest = submission_manifest(workspace)  # Also rejects symlinked submissions.
    (output.parent / "submission-manifest.json").write_text(json.dumps({"files": manifest}, indent=2) + "\n")
    reason = guard_reason(rubric, workspace)
    if reason is not None:
        result = write_guard_result(rubric, output, reason)
        details = json.loads(details_path.read_text())
        details["reward"]["measurement"] = measurement(plan)
        details['reward']['passed'] = False
        details_path.write_text(json.dumps(details, indent=2) + "\n")
        return result

    scores = programmatic_scores(definitions, plan, catalog, workspace, rubric.parent)
    rows = {score.name: score.to_dict() for score in scores}
    source_definitions = [c for c in definitions if plan["checks"][c["id"]]["kind"] == "ai-review"]
    source_detail = None
    if source_definitions:
        with tempfile.TemporaryDirectory(prefix="expo-kit-judge-") as temporary:
            prepared = prepare_rubric(rubric, Path(temporary) / "rubric", workspace,
                                      os.getenv("REWARDKIT_JUDGE") or None, os.getenv("REWARDKIT_MODEL") or None)
            source_config = tomllib.loads((prepared / "reward.toml").read_text())
            source_config["criterion"] = source_definitions
            source_config['scoring'] = {'aggregation': 'weighted-sum'}
            (prepared / "reward.toml").write_text(tomli_w.dumps(source_config))
            source_output = Path(temporary) / "reward.json"
            run(prepared, workspace=workspace, output=source_output)
            reject_judge_errors(source_output)
            source_detail = json.loads((source_output.parent / "reward-details.json").read_text())["reward"]
            source_rows = source_detail["criteria"]
            if len(source_rows) != len(source_definitions) or {r.get("id") for r in source_rows} != {c["id"] for c in source_definitions}:
                raise ValueError("Judge must return every source criterion exactly once")
            rows.update({r["id"]: r for r in source_rows})

    ordered = []
    for definition in definitions:
        key = definition["id"]
        row = rows[key]
        if row.get('error') or isinstance(row["value"], bool) or not isinstance(row["value"], (int, float)) or not math.isfinite(row["value"]) or not 0 <= row['value'] <= 1:
            raise ValueError(f"Invalid normalized result for {key}")
        if definition.get('type', 'binary') == 'binary' and row['value'] not in (0, 1):
            raise ValueError(f"Invalid binary result for {key}")
        if definition.get('negate') and plan['checks'][key]['kind'] != 'ai-review':
            row = {**row, 'value': 1 - row['value']}
        ordered.append({**row, "id": key, "name": definition["name"], "description": definition["description"],
                        "weight": definition["weight"], 'optional': definition.get('optional', False),
                        'negate': definition.get('negate', False), "evaluator": plan["checks"][key]["kind"]})
    # One aggregation across individual checks, never an average of differently sized groups.
    scoring = scoring_config(plan)
    score = round(aggregate_scores([Score.model_validate(row) for row in ordered], **scoring), 4)
    details = {"reward": {"score": score, "criteria": ordered, "measurement": measurement(plan), **scoring}}
    maximum = sum(max(0, row['weight']) for row in ordered) if scoring['aggregation'] == 'weighted-sum' else 1.0
    details['reward']['passed'] = math.isclose(score, round(maximum, 4), abs_tol=1e-6)
    if source_detail is not None:
        details["source_review"] = source_detail
    details_path.write_text(json.dumps(details, indent=2) + "\n")
    output.write_text(json.dumps({"reward": score}, indent=2) + "\n")
    return {"reward": score}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rubric", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(run_grading(args.rubric, args.workspace, args.output))


if __name__ == "__main__":
    main()
