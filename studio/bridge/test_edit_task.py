"""Real task edit regressions, entirely inside temporary repositories."""
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import catalog
import edit_task
from expo_harbor_evals.evaluation_identity import make_suite, task_digest
from expo_harbor_evals.codegen_rewardkit_runner import submission_manifest

SOURCE = Path(__file__).resolve().parents[2]
PAYWALL = "feedback-11-anonymous-paywall-eligibility"


class TaskEditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="studio-edit-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for module in (catalog, edit_task):
            replacement = patch.object(module, "ROOT", self.root)
            replacement.start()
            self.addCleanup(replacement.stop)

    def fixture(self, task=PAYWALL, family="codegen"):
        target = self.root / "tasks" / family / task
        shutil.copytree(SOURCE / "tasks" / family / task, target)
        self.suite = self.root / "suites/mobile-v2.json"
        self.suite.parent.mkdir(exist_ok=True)
        self.suite.write_text(json.dumps(make_suite(self.root)))
        return target, edit_task.load_edit(task)

    def test_edit_preserves_policy_verifier_and_versions_only_the_edited_task(self):
        task, edit = self.fixture()
        originals = {rel: (task / rel).read_bytes() for rel in (
            "tests/contract.cjs", "tests/run_rewardkit.py", "tests/requirements/behavior.json", "environment/Dockerfile", "solution/solve.sh",
        )}
        suite_before = json.loads(self.suite.read_text())
        draft = edit["draft"]
        draft["title"] = "Anonymous eligibility regression"
        draft["instruction"] += "\nPreserve all identity guards.\n"
        draft["criteria"][0]["description"] += " Do not trust comments as evidence."
        result = edit_task.update_task(PAYWALL, edit["fingerprint"], draft)
        self.assertEqual(result["draft"]["title"], draft["title"])
        self.assertNotEqual(result["fingerprint"], edit["fingerprint"])
        self.assertEqual(result["draft"]["revision"], 1)
        for relative, content in originals.items():
            self.assertEqual((task / relative).read_bytes(), content, relative)
        self.assertEqual(json.loads(self.suite.read_text()), make_suite(self.root))
        self.assertEqual(json.loads(self.suite.read_text())["engine"], suite_before["engine"])
        self.assertEqual(tomllib.loads((task / "task.toml").read_text())["metadata"]["validation_status"], "requires-calibration")
        self.assertEqual(json.loads((task / "tests/requirements/baseline-manifest.json").read_text())["files"], submission_manifest(task / "environment"))

    def test_conflicting_edits_and_grader_replacement_fail_without_writes(self):
        task, edit = self.fixture()
        draft = deepcopy(edit["draft"])
        draft["criteria"][0]["grading"] = {"kind": "file-exists", "config": {"path": "App.tsx"}}
        with self.assertRaisesRegex(ValueError, "native or policy verifier"):
            edit_task.update_task(PAYWALL, edit["fingerprint"], draft)
        self.assertEqual(task_digest(task), edit["fingerprint"])
        (task / "instruction.md").write_text("Another editor changed this task.")
        latest = task_digest(task)
        with self.assertRaisesRegex(ValueError, "changed since"):
            edit_task.update_task(PAYWALL, edit["fingerprint"], edit["draft"])
        self.assertEqual(task_digest(task), latest)

    def test_edit_rolls_back_if_suite_write_fails(self):
        task, edit = self.fixture()
        suite = self.suite.read_bytes()
        edit["draft"]["title"] = "Should roll back"
        original_replace = Path.replace
        def replace(path, target):
            if target == self.suite:
                raise OSError("fixture write failure")
            return original_replace(path, target)
        with patch.object(Path, "replace", replace):
            with self.assertRaisesRegex(OSError, "fixture write failure"):
                edit_task.update_task(PAYWALL, edit["fingerprint"], edit["draft"])
        self.assertEqual(task_digest(task), edit["fingerprint"])
        self.assertEqual(self.suite.read_bytes(), suite)

    def test_active_run_prevents_task_mutation(self):
        task, edit = self.fixture()
        state = self.root / ".studio"
        state.mkdir()
        with (state / "execution.lock").open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "local run or edit"):
                edit_task.update_task(PAYWALL, edit["fingerprint"], edit["draft"])
        self.assertEqual(task_digest(task), edit["fingerprint"])

    def test_native_brief_edit_keeps_shared_app_verifier_and_hold(self):
        name = "simbench-ios-10-goldengate-browser-handoff"
        task, edit = self.fixture(name, "simbench")
        before = {str(p.relative_to(task)): p.read_bytes() for p in task.rglob("*") if p.is_file() and p.name not in {"task.toml", "instruction.md"}}
        edit["draft"]["instruction"] += "\nComplete the callback before finishing.\n"
        result = edit_task.update_task(name, edit["fingerprint"], edit["draft"])
        self.assertEqual(result["family"], "simbench")
        for relative, content in before.items():
            self.assertEqual((task / relative).read_bytes(), content)
        self.assertTrue(tomllib.loads((task / "task.toml").read_text())["metadata"]["validation_status"].startswith("held"))

    def test_source_task_can_adopt_a_recipe_and_return_to_source_review(self):
        name = "router-02-stack-layout-not-native-stack-import"
        task, edit = self.fixture(name)
        source = self.root / "src/expo_harbor_evals"
        source.mkdir(parents=True)
        shutil.copyfile(SOURCE / "src/expo_harbor_evals/codegen_rewardkit_runner.py", source / "codegen_rewardkit_runner.py")
        edit["draft"]["criteria"][0]["grading"] = {"kind": "file-exists", "config": {"path": "App.tsx"}}
        changed = edit_task.update_task(name, edit["fingerprint"], edit["draft"])
        self.assertEqual(catalog.task_record(task)["measurements"], ["source-and-checks"])
        self.assertEqual((task / "tests/run_rewardkit.py").read_bytes(), (SOURCE / "graders/kit_runner.py").read_bytes())
        self.assertEqual(changed["draft"]["criteria"][0]["grading"]["kind"], "file-exists")
        changed["draft"]["criteria"][0]["grading"] = {"kind": "ai-review", "config": {}}
        edit_task.update_task(name, changed["fingerprint"], changed["draft"])
        self.assertFalse((task / "tests/requirements/grading.json").exists())
        self.assertFalse((task / "tests/source_runner.py").exists())
        self.assertEqual((task / "tests/run_rewardkit.py").read_bytes(), (source / "codegen_rewardkit_runner.py").read_bytes())

    def test_edit_rejects_symlinked_hidden_assets(self):
        task, edit = self.fixture()
        outside = self.root / "outside.txt"
        outside.write_text("private fixture")
        (task / ".hidden").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            edit_task.load_edit(PAYWALL)

    def test_editor_round_trips_scoring_and_fractional_check_settings(self):
        name = 'router-07-protected-routes-auth'
        task, edit = self.fixture(name)
        source = self.root / 'src/expo_harbor_evals'
        source.mkdir(parents=True)
        shutil.copyfile(SOURCE / 'src/expo_harbor_evals/codegen_rewardkit_runner.py', source / 'codegen_rewardkit_runner.py')
        draft = edit['draft']
        draft['scoring'] = {'aggregation': 'threshold', 'threshold': 0.8}
        draft['criteria'][0].update(type='numeric', min=0, max=1, optional=True, negate=True,
            grading={'kind': 'diff-ratio', 'config': {'path': 'App.tsx', 'expected': 'fixture'}})
        updated = edit_task.update_task(name, edit['fingerprint'], draft)
        loaded = edit_task.load_edit(name)['draft']
        self.assertEqual(loaded['scoring'], draft['scoring'])
        self.assertEqual(loaded['criteria'][0]['grading'], draft['criteria'][0]['grading'])
        self.assertEqual(loaded['criteria'][0]['type'], 'numeric')
        self.assertTrue(loaded['criteria'][0]['optional'])
        self.assertTrue(loaded['criteria'][0]['negate'])
        self.assertEqual(json.loads((task / 'tests/requirements/grading.json').read_text())['scoring'], draft['scoring'])
