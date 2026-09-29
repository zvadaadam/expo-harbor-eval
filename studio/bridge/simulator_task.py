"""Author simulator scenarios from complete, versioned repository fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import re
import plistlib
import shutil
import tempfile

import tomli_w
import tomllib

from catalog import ROOT, contained, task_dir, task_record
from expo_harbor_evals.evaluation_identity import task_digest
from expo_harbor_evals.metadata import TIERS


AREAS = {'environment': 'environment', 'reference': 'solution', 'checks': 'tests'}


def allowed_file(area: str, path: str) -> bool:
    if not path or '\\' in path or '\0' in path or any(not part or part == '..' or part.startswith('.') for part in path.split('/')):
        return False
    if area == 'environment':
        return path.startswith('app-src/')
    if area == 'reference':
        return path.endswith('.py')
    if area == 'checks':
        return path.endswith(('.py', '.json')) and path != 'simbench_evidence.py'
    return False


def template_snapshot(task_id: str) -> dict:
    source = task_dir(task_id)
    # Validate the full copy, including files not exposed in the editor.
    for path in source.rglob('*'):
        contained(ROOT, path)
    fingerprint = task_digest(source)
    task = task_record(source, True)
    if task['family'] != 'simbench':
        raise ValueError('Choose a simulator task')
    files = []
    for area, folder in AREAS.items():
        for path in sorted((source / folder).rglob('*')):
            relative = path.relative_to(source / folder).as_posix()
            if path.is_file() and allowed_file(area, relative):
                content = path.read_text()
                if len(content.encode()) > 200_000:
                    raise ValueError('Simulator file exceeds the editor limit')
                files.append({'area': area, 'path': relative, 'content': content})
    if task_digest(source) != fingerprint:
        raise ValueError('The simulator template changed while loading; try again')
    return {'task': task, 'files': files,
            'simulator': {'template': task_id, 'fingerprint': fingerprint, 'tier': task['tier']}}


def write_scenario_files(stage: Path, draft: dict) -> None:
    seen = set()
    for file in draft['files']:
        area, name = file['area'], file['path']
        if not allowed_file(area, name) or (area, name) in seen:
            raise ValueError('Invalid simulator file or duplicate path')
        seen.add((area, name))
        target = contained(stage, stage / AREAS[area] / name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file['content'])
    for required in (('checks', 'verify.py'), ('reference', 'oracle.py')):
        if required not in seen or not (stage / AREAS[required[0]] / required[1]).read_text().strip():
            raise ValueError('Keep a simulator verifier and reference UI automation')
    try:
        info = plistlib.loads((stage / 'environment/app-src/Info.plist').read_bytes())
        executable = info['CFBundleExecutable']
        if not info['CFBundleIdentifier'] or not re.fullmatch(r'[A-Za-z0-9_-]+', executable) or not (stage / 'environment/app-src' / f'{executable}.swift').is_file():
            raise ValueError('Missing simulator app source')
    except (OSError, KeyError, plistlib.InvalidFileException) as exc:
        raise ValueError('Keep a valid simulator Info.plist and matching Swift app source') from exc


def export_simulator(draft: dict, root: Path) -> dict:
    scenario = draft.get('simulator')
    if not scenario:
        raise ValueError('Choose a simulator scenario')
    snapshot = template_snapshot(scenario['template'])
    if snapshot['simulator']['fingerprint'] != scenario['fingerprint']:
        raise ValueError('The simulator template changed. Load the scenario again before exporting.')
    if scenario['tier'] not in TIERS - {'code-gen'}:
        raise ValueError('Unknown simulator scenario type')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', draft['slug']) or not re.fullmatch(r'[a-f0-9-]{36}', draft['id']):
        raise ValueError('Invalid task or draft ID')
    if draft['criteria']:
        raise ValueError('Simulator scenarios use their app-state verifier')
    parent = contained(root, root / 'outputs/studio' / draft['id'] / str(int(draft['revision'])))
    target = parent / draft['slug']
    if target.exists():
        raise ValueError('This revision is already exported. Save a new revision to export changes.')
    parent.mkdir(parents=True, exist_ok=True)
    source = task_dir(scenario['template'])
    with tempfile.TemporaryDirectory(prefix='.export-', dir=parent) as temporary:
        stage = Path(temporary) / draft['slug']
        shutil.copytree(source, stage)
        # Replace exactly the editable template files. Drivers and evidence collection stay intact.
        for file in snapshot['files']:
            (stage / AREAS[file['area']] / file['path']).unlink()
        write_scenario_files(stage, draft)
        (stage / 'instruction.md').write_text(draft['instruction'].rstrip() + '\n')
        config = tomllib.loads((stage / 'task.toml').read_text())
        config['task'].update(name='expo-harbor/' + draft['slug'], description=draft['title'])
        config['metadata'].update(title=draft['title'], category='simbench', family='simbench', tier=scenario['tier'],
            difficulty=draft['difficulty'], motivation=draft['motivation'], template=scenario['template'],
            reference_validation='Exported from Studio. Simulator controls have not been run.')
        if not snapshot['task']['held']:
            config['metadata']['validation_status'] = 'requires-simulator-calibration'
        (stage / 'task.toml').write_text(tomli_w.dumps(config))
        # The evidence helper records the task ID; update its entry-point label without touching assertions.
        verify = stage / 'tests/verify.py'
        verify.write_text(verify.read_text().replace(repr(scenario['template']), repr(draft['slug'])).replace(json.dumps(scenario['template']), json.dumps(draft['slug'])))
        (stage / 'studio-scenario.json').write_text(json.dumps(scenario, indent=2) + '\n')
        from expo_harbor_evals.simbench_calibrate import calibration_config
        import yaml
        calibration = calibration_config(root, scenario['template'], 1)
        calibration['environment']['kwargs'] = {'allow_unversioned_tasks': True}
        calibration['jobs_dir'] = str(root / 'runs')
        calibration['datasets'] = [{'path': str(parent), 'task_names': [draft['slug']]}]
        (stage / 'calibration.yaml').write_text(yaml.safe_dump(calibration, sort_keys=False))
        from harbor.models.task.config import TaskConfig
        TaskConfig.model_validate(config)
        if task_digest(source) != scenario['fingerprint']:
            raise ValueError('The simulator template changed during export')
        target.mkdir()
        try:
            for child in stage.iterdir():
                child.rename(target / child.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    return {'path': str(target.relative_to(root)), 'files': sorted(str(p.relative_to(target)) for p in target.rglob('*') if p.is_file())}
