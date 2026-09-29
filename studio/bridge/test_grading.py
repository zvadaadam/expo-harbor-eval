"""Exercise the exported RewardKit verifier, without a model or simulator."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import unittest
from unittest.mock import patch

import export_task
import test_export


class GradingTests(unittest.TestCase):
    # Reuse the isolated export fixture; these checks never mutate real tasks.
    setUp = test_export.ExportAndGuardTests.setUp
    export = test_export.ExportAndGuardTests.export
    def programmatic(self):
        self.draft["criteria"] = [
            {"id": "ready-state", "name": "ready-state", "description": "Ready is true", "weight": 1,
             "grading": {"kind": "json-key-equals", "config": {"path": "result.json", "key": "ready", "expected": "true"}}},
            {"id": "listener-cleanup", "name": "listener-cleanup", "description": "Listener is removed", "weight": 3,
             "grading": {"kind": "test-script", "config": {"script": "cleanup.py"}}},
            {"id": "has-file", "name": "has-file", "description": "Result file exists", "weight": 1,
             "grading": {"kind": "file-exists", "config": {"path": "result.json"}}},
            {"id": "has-text", "name": "has-text", "description": "Result contains ready", "weight": 1,
             "grading": {"kind": "file-contains", "config": {"path": "result.json", "text": "ready"}}},
        ]
        for area, ready, cleanup in (("environment", False, False), ("reference", True, True), ("distractor", True, False)):
            self.draft["files"].append({"area": area, "path": "result.json", "content": json.dumps({"ready": ready, "cleanup": cleanup})})
        self.draft["files"].append({"area": "checks", "path": "cleanup.py", "content":
            "import json, os, sys\nfrom pathlib import Path\nassert 'ANTHROPIC_API_KEY' not in os.environ\n"
            "assert 'PYTHONPATH' not in os.environ\nassert json.loads((Path(sys.argv[1]) / 'result.json').read_text())['cleanup']\n"})
        return self.export()

    def run_export(self, task, bracket):
        app = self.root / "scratch" / bracket / "app"
        app.mkdir(parents=True)
        if bracket != "empty":
            shutil.copytree(task / "environment", app, dirs_exist_ok=True)
        if bracket in {"reference", "distractor"}:
            shutil.copytree(task / "solution" / bracket, app, dirs_exist_ok=True)
        if bracket == "baseline-comment":
            with (app / "App.tsx").open("a") as f:
                f.write("\n// Still broken.\n")
        output = app.parent / "reward.json"
        result = subprocess.run([sys.executable, str(task / "tests/run_rewardkit.py"), str(task / "tests/requirements"), str(app), str(output)],
            capture_output=True, text=True, timeout=30,
            env={"PATH": os.environ.get("PATH", os.defpath), "REWARDKIT_JUDGE": "must-not-run", "ANTHROPIC_API_KEY": "test-sentinel"})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(output.read_text()), json.loads((output.parent / "reward-details.json").read_text())["reward"]

    def test_every_programmatic_recipe_runs_real_rewardkit_and_calibrates(self):
        from expo_harbor_evals.codegen_calibrate import assess_bracket
        task = self.programmatic()
        self.assertEqual(tomllib.loads((task / "task.toml").read_text())["metadata"]["measurement"], "programmatic-checks")
        self.assertFalse((task / "environment/cleanup.py").exists())
        for bracket in ("empty", "baseline", "reference", "baseline-comment", "distractor"):
            with self.subTest(bracket=bracket):
                result, detail = self.run_export(task, bracket)
                self.assertEqual(detail["measurement"], "programmatic-checks")
                self.assertEqual(len(detail["criteria"]), 4)
                ok, note = assess_bracket(task, bracket, {"reward": result["reward"], "criteria": detail["criteria"], "guarded": "guard" in detail})
                self.assertTrue(ok, note)
                if bracket == "distractor":
                    self.assertEqual(result["reward"], 0.5)

    def test_mixed_grading_only_judges_ai_checks_and_weights_each_criterion(self):
        task = self.programmatic()
        plan_path = task / "tests/requirements/grading.json"
        plan = json.loads(plan_path.read_text())
        plan["checks"]["has-text"] = {"kind": "ai-review", "config": {}}
        plan_path.write_text(json.dumps(plan))
        spec = importlib.util.spec_from_file_location("exported_kit", task / "tests/run_rewardkit.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source_spec = importlib.util.spec_from_file_location("source_runner", task / "tests/source_runner.py")
        source = importlib.util.module_from_spec(source_spec)
        source_spec.loader.exec_module(source)
        app = self.root / "mixed"
        shutil.copytree(task / "environment", app)
        shutil.copytree(task / "solution/reference", app, dirs_exist_ok=True)
        output = self.root / "mixed-result/reward.json"
        judged_type = 'binary'
        judged_value = 0
        def fake_judge(prepared, *, workspace, output):
            rubric = tomllib.loads((prepared / "reward.toml").read_text())
            self.assertEqual([c["id"] for c in rubric["criterion"]], ["has-text"])
            self.assertEqual(rubric['criterion'][0]['type'], judged_type)
            output.write_text('{"reward":0}')
            (output.parent / "reward-details.json").write_text(json.dumps({"reward": {"score": 0, "criteria": [{"id": "has-text", "name": "has-text", "value": judged_value, "raw": judged_value, "weight": 1}]}}))
        with patch.dict(sys.modules, {"source_runner": source}), patch("rewardkit.runner.run", side_effect=fake_judge) as judge:
            self.assertEqual(module.run_grading(task / "tests/requirements", app, output), {"reward": 0.8333})
            judge.assert_called_once()
        detail = json.loads((output.parent / "reward-details.json").read_text())
        self.assertEqual(detail["reward"]["measurement"], "source-and-checks")
        self.assertIn("source_review", detail)
        # AI scoring formats are passed through to upstream, with normalized partial credit retained.
        import tomli_w
        rubric_path = task / 'tests/requirements/rubric.toml'
        for judged_type in ('likert', 'numeric'):
            rubric = tomllib.loads(rubric_path.read_text())
            rubric['criterion'][-1].update(type=judged_type, points=5, min=0, max=10)
            rubric_path.write_text(tomli_w.dumps(rubric))
            judged_value = 0.5
            with patch.dict(sys.modules, {'source_runner': source}), patch('rewardkit.runner.run', side_effect=fake_judge):
                self.assertEqual(module.run_grading(task / 'tests/requirements', app, output), {'reward': 0.9167})
        # A failed judge must not leave the previous successful score behind.
        with patch.dict(sys.modules, {"source_runner": source}), patch("rewardkit.runner.run", side_effect=RuntimeError("judge unavailable")):
            with self.assertRaisesRegex(RuntimeError, "judge unavailable"):
                module.run_grading(task / "tests/requirements", app, output)
        self.assertFalse(output.exists())

    def test_export_rejects_unknown_incomplete_and_escaping_recipes(self):
        for recipe in (
            {"kind": "invented", "config": {}},
            {"kind": "file-exists", "config": {}},
            {"kind": "file-exists", "config": {"path": "../secret"}},
            {"kind": "json-key-equals", "config": {"path": "a.json", "key": "x", "expected": "NaN"}},
            {"kind": "test-script", "config": {"script": "missing.py"}},
        ):
            with self.subTest(recipe=recipe):
                draft = deepcopy(self.draft)
                draft["criteria"][0]["grading"] = recipe
                with self.assertRaises(ValueError):
                    export_task.export_task(draft)

    def test_all_aggregations_use_upstream_weights_optional_and_negation(self):
        for index, (aggregation, expected) in enumerate([
            ('weighted-mean', 0.4), ('weighted-sum', 2), ('all-pass', 0),
            ('any-pass', 1), ('required-pass', 1), ('threshold', 0),
        ]):
            with self.subTest(aggregation=aggregation):
                self.draft['revision'] = index + 1
                self.draft['scoring'] = {'aggregation': aggregation, 'threshold': 0.5}
                self.draft['criteria'] = [
                    {'id': 'ready-state', 'name': 'ready-state', 'description': 'App present', 'weight': 2,
                     'grading': {'kind': 'file-exists', 'config': {'path': 'App.tsx'}}},
                    {'id': 'listener-cleanup', 'name': 'listener-cleanup', 'description': 'Inverted check', 'weight': 3, 'optional': True, 'negate': True,
                     'grading': {'kind': 'file-exists', 'config': {'path': 'App.tsx'}}},
                ]
                task = self.export()
                # Use a fresh output directory for each verifier run.
                original_root = self.root
                self.root = original_root / str(index)
                try:
                    result, detail = self.run_export(task, 'reference')
                finally:
                    self.root = original_root
                self.assertEqual(result['reward'], expected)
                self.assertEqual(detail['aggregation'], aggregation)
                self.assertEqual(detail['criteria'][1]['value'], 0)
                self.assertTrue(detail['criteria'][1]['optional'])

    def test_continuous_scores_export_execute_and_calibrate(self):
        self.draft['criteria'] = [
            {'id': 'ready-state', 'name': 'ready-state', 'description': 'Expected text', 'weight': 1,
             'grading': {'kind': 'diff-ratio', 'config': {'path': 'answer.txt', 'expected': 'aaaa'}}},
            {'id': 'listener-cleanup', 'name': 'listener-cleanup', 'description': 'Clean state', 'weight': 1,
             'grading': {'kind': 'file-contains', 'config': {'path': 'answer.txt', 'text': 'aaaa'}}},
        ]
        for area, value in [('environment', 'zzzz'), ('reference', 'aaaa'), ('distractor', 'bbbb')]:
            self.draft['files'].append({'area': area, 'path': 'answer.txt', 'content': value})
        task = self.export()
        from expo_harbor_evals.codegen_calibrate import assess_bracket
        for bracket in ('empty', 'baseline', 'reference', 'baseline-comment', 'distractor'):
            result, detail = self.run_export(task, bracket)
            ok, reason = assess_bracket(task, bracket, {'reward': result['reward'], 'criteria': detail['criteria'], 'guarded': 'guard' in detail})
            self.assertTrue(ok, reason)
        (task / 'solution/reference/answer.txt').write_text('aabb')
        original_root = self.root
        self.root = original_root / 'partial'
        try:
            result, detail = self.run_export(task, 'reference')
        finally:
            self.root = original_root
        self.assertEqual(detail['criteria'][0]['value'], 0.5)
        self.assertEqual(result['reward'], 0.25)
        self.assertFalse(detail['passed'])

    def test_negative_weight_penalties_calibrate_against_the_wrong_behavior(self):
        from expo_harbor_evals.codegen_calibrate import assess_bracket
        self.draft['scoring'] = {'aggregation': 'weighted-sum', 'threshold': 0.5}
        self.draft['criteria'] = [
            {'id': 'ready-state', 'name': 'ready-state', 'description': 'App present', 'weight': 2,
             'grading': {'kind': 'file-exists', 'config': {'path': 'App.tsx'}}},
            {'id': 'listener-cleanup', 'name': 'listener-cleanup', 'description': 'Forbidden API penalty', 'weight': -1,
             'grading': {'kind': 'file-contains', 'config': {'path': 'answer.txt', 'text': 'forbidden'}}},
        ]
        self.draft['mustFail'] = self.draft['baselineMustFail'] = ['listener-cleanup']
        for area, value in [('environment', 'forbidden'), ('reference', 'allowed'), ('distractor', 'forbidden')]:
            self.draft['files'].append({'area': area, 'path': 'answer.txt', 'content': value})
        task = self.export()
        for bracket in ('empty', 'baseline', 'reference', 'baseline-comment', 'distractor'):
            with self.subTest(bracket=bracket):
                result, detail = self.run_export(task, bracket)
                ok, reason = assess_bracket(task, bracket, {'reward': result['reward'], 'criteria': detail['criteria'], 'guarded': 'guard' in detail})
                self.assertTrue(ok, reason)
                self.assertEqual(detail['passed'], bracket == 'reference')
        # An unrelated lost point still cannot establish a penalty's calibration.
        self.assertFalse(assess_bracket(task, 'distractor', {'reward': 0, 'guarded': False,
            'criteria': [{'id': 'ready-state', 'value': 0}, {'id': 'listener-cleanup', 'value': 0}]})[0])
