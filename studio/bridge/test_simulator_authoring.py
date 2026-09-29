"""Simulator authoring keeps a complete runnable fixture and honest provenance."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from uuid import uuid4

import yaml
import catalog
import export_task
import simulator_task
import test_export

from expo_harbor_evals.metadata import TIERS, CATEGORIES
from harbor.models.task.config import TaskConfig

SOURCE = Path(__file__).resolve().parents[2]


class SimulatorAuthoringTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='studio-simulator-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        shutil.copytree(SOURCE / 'tasks/simbench', self.root / 'tasks/simbench')
        for module in (catalog, export_task, simulator_task):
            replacement = patch.object(module, 'ROOT', self.root)
            replacement.start()
            self.addCleanup(replacement.stop)

    def draft(self, task_id):
        snapshot = simulator_task.template_snapshot(task_id)
        task = snapshot['task']
        return {**test_export.draft_fixture(), 'id': str(uuid4()), 'slug': 'new-' + task_id,
                'category': 'simbench', 'sourceTask': task_id, 'simulator': snapshot['simulator'],
                'criteria': [], 'files': snapshot['files'], 'instruction': task['instruction'],
                'mustFail': [], 'baselineMustFail': []}

    def test_all_scenarios_export_with_drivers_verifiers_oracles_and_controls(self):
        for source in sorted((self.root / 'tasks/simbench').iterdir()):
            with self.subTest(task=source.name):
                draft = self.draft(source.name)
                exported = export_task.export_task(draft)
                target = self.root / exported['path']
                config = tomllib.loads((target / 'task.toml').read_text())
                TaskConfig.model_validate(config)
                self.assertEqual(config['metadata']['family'], 'simbench')
                self.assertEqual(config['metadata']['tier'], draft['simulator']['tier'])
                self.assertEqual(config['task']['name'], 'expo-harbor/' + draft['slug'])
                for path in ('environment/driver/setup.sh', 'tests/test.sh', 'tests/simbench_evidence.py', 'solution/solve.sh'):
                    self.assertEqual((target / path).read_bytes(), (source / path).read_bytes())
                for path in ('tests/verify.py', 'solution/oracle.py'):
                    ast.parse((target / path).read_text())
                calibration = yaml.safe_load((target / 'calibration.yaml').read_text())
                from harbor.models.job.config import JobConfig
                JobConfig.model_validate(calibration)
                self.assertTrue(calibration['environment']['kwargs']['allow_unversioned_tasks'])
                self.assertEqual(calibration['datasets'][0]['task_names'], [draft['slug']])
                self.assertEqual([agent['name'] for agent in calibration['agents'][:2]], ['nop', 'oracle'])
                if 'shift-flow' in source.name:
                    self.assertEqual(calibration['agents'][2]['model_name'], 'out-of-order')
                if 'system-auth-session' in source.name:
                    self.assertEqual(calibration['agents'][2]['model_name'], 'consent-denied')
                if 'browser-handoff' in source.name:
                    self.assertTrue(config['metadata']['validation_status'].startswith('held'))
                else:
                    self.assertEqual(config['metadata']['validation_status'], 'requires-simulator-calibration')

    def test_edited_simulator_check_rejects_direct_state_injection(self):
        draft = self.draft('simbench-ios-01-goldennotes-create-note')
        for file in draft['files']:
            file['content'] = file['content'].replace('Harbor Sim Bench 001', 'Studio authored note')
        draft['instruction'] = draft['instruction'].replace('Harbor Sim Bench 001', 'Studio authored note')
        target = self.root / export_task.export_task(draft)['path']
        spec = importlib.util.spec_from_file_location('authored_verifier', target / 'tests/verify.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        self.assertEqual(verifier.TARGET_TITLE, 'Studio authored note')
        container = self.root / 'container'
        (container / 'Documents').mkdir(parents=True)
        def read(path, default):
            return json.loads(path.read_text()) if path.exists() else default
        def passes():
            checks, _, _ = verifier.build_checks(container, read)
            return all(check['passed'] for check in checks)
        self.assertFalse(passes())
        (container / 'Documents/notes.json').write_text('[{"title":"Studio authored note"}]')
        self.assertFalse(passes(), 'Injected state must not pass without a UI event')
        (container / 'Documents/events.json').write_text('[{"kind":"add-note-ui","title":"Studio authored note"}]')
        self.assertTrue(passes())
        self.assertIn('Studio authored note', (target / 'solution/oracle.py').read_text())

    def test_stale_template_and_managed_file_overrides_are_rejected(self):
        draft = self.draft('simbench-ios-01-goldennotes-create-note')
        unsafe = deepcopy(draft)
        unsafe['files'].append({'area': 'checks', 'path': 'simbench_evidence.py', 'content': 'override'})
        with self.assertRaisesRegex(ValueError, 'Invalid simulator file'):
            export_task.export_task(unsafe)
        (self.root / 'tasks/simbench' / draft['sourceTask'] / 'instruction.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'template changed'):
            export_task.export_task(draft)

    def test_scenario_types_match_repository_metadata(self):
        types = json.loads((SOURCE / 'studio/src/lib/simulator-tiers.json').read_text())
        self.assertEqual(set(types), TIERS - {'code-gen'})
        self.assertEqual(CATEGORIES, {'expo-feedback', 'expo-sdk', 'expo-router', 'expo-ui', 'simbench'})

    def test_template_loads_in_a_fresh_bridge_process(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(SOURCE / 'studio/bridge/catalog.py')],
            input=json.dumps({'action': 'simulator-template', 'task': 'simbench-ios-01-goldennotes-create-note'}),
            capture_output=True, text=True, timeout=15, check=True)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot['task']['family'], 'simbench')
        self.assertIn('verify.py', [f['path'] for f in snapshot['files']])
