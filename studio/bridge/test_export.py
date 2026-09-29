"""Regressions for reviewable task exports and genuinely free guard checks."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import tomllib
import types
import unittest
from unittest.mock import Mock, patch

import catalog
import export_task
import guards
from expo_harbor_evals import codegen_calibrate, codegen_scaffold
from expo_harbor_evals.codegen_rewardkit_runner import guard_reason, submission_manifest

try:
    from harbor.models.task.config import TaskConfig
except ImportError:
    TaskConfig = None
try:
    from rewardkit.models import JudgeTomlConfig
except ImportError:
    JudgeTomlConfig = None


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def draft_fixture() -> dict:
    return {
        "id": "82b99f6e-0097-4d18-ad72-e3cc2645a70b", "revision": 1,
        "slug": "studio-control-regression", "title": 'Restore "ready" state — Expo',
        "category": "expo-ui", "difficulty": "medium",
        "motivation": "State survives navigation.\nListeners must be cleaned up.",
        "instruction": "Restore the ready state and clean up the listener when the screen unmounts.",
        "sourceTask": None, "updatedAt": "2026-09-24T00:00:00Z",
        "criteria": [
            {"id": "ready-state", "name": "ready-state", "description": 'Shows the "ready" state.\nPreserve the screen.', "weight": 1},
            {"id": "listener-cleanup", "name": "listener-cleanup", "description": "The listener is removed on unmount.", "weight": 3},
        ],
        # The baseline and the plausible wrong fix fail different criteria.
        "baselineMustFail": ["ready-state"], "mustFail": ["listener-cleanup"],
        "files": [
            {"area": "environment", "path": "App.tsx", "content": "export default function App() { return null; }\n"},
            {"area": "environment", "path": "src/state.ts", "content": "export const ready = false;\n"},
            {"area": "environment", "path": "package.json", "content": '{"private":true}\n'},
            {"area": "environment", "path": "node_modules/fixture/index.js", "content": "module.exports = {};\n"},
            {"area": "environment", "path": "src/node_modules/nested/index.js", "content": "module.exports = {};\n"},
            {"area": "environment", "path": "__pycache__/fixture.txt", "content": "ignored cache\n"},
            {"area": "reference", "path": "App.tsx", "content": "export default function App() { return <ReadyScreen />; }\n"},
            {"area": "reference", "path": "src/state.ts", "content": "export const ready = true;\n"},
            {"area": "distractor", "path": "App.tsx", "content": "export default function App() { subscribe(); return <ReadyScreen />; }\n"},
        ],
    }


class ExportAndGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="studio-export-test-")
        self.addCleanup(temporary.cleanup)
        # Resolve /var on macOS: production deliberately rejects symlink parents.
        self.root = Path(temporary.name).resolve()
        source = self.root / "src/expo_harbor_evals"
        source.mkdir(parents=True)
        for name in ("codegen_rewardkit_runner.py", "codegen_reference_check.py"):
            shutil.copyfile(SOURCE_ROOT / "src/expo_harbor_evals" / name, source / name)
        for module in (catalog, export_task):
            replacement = patch.object(module, "ROOT", self.root)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.draft = draft_fixture()

    def export(self) -> Path:
        result = export_task.export_task(self.draft)
        task = self.root / result["path"]
        self.assertEqual(result["files"], sorted(str(p.relative_to(task)) for p in task.rglob("*") if p.is_file()))
        return task

    def test_export_preserves_contracts_and_shared_scaffolding(self):
        task = self.export()
        config = tomllib.loads((task / "task.toml").read_text())
        rubric = tomllib.loads((task / "tests/requirements/rubric.toml").read_text())
        self.assertEqual(config["task"]["description"], self.draft["title"])
        self.assertEqual(config["metadata"]["motivation"], self.draft["motivation"])
        self.assertEqual(config["metadata"]["family"], "expo-codegen")
        self.assertEqual(config["metadata"]["validation_status"], "requires-judge-calibration")
        self.assertEqual(config["verifier"]["environment_mode"], "separate")
        self.assertEqual(config["environment"]["workdir"], "/app")
        self.assertIn(".env.*", config["artifacts"][0]["exclude"])
        self.assertEqual(rubric["criterion"], [{**criterion, "type": "binary"} for criterion in self.draft["criteria"]])
        self.assertEqual(rubric["scoring"], {"aggregation": "weighted-mean", "threshold": 0.5})
        self.assertEqual((task / "instruction.md").read_text(), self.draft["instruction"] + "\n")
        templates = {
            "environment/Dockerfile": "DOCKERFILE", "tests/Dockerfile": "VERIFIER_DOCKERFILE",
            "tests/test.sh": "TEST_SH", "solution/solve.sh": "SOLUTION_SH",
            "tests/requirements/judge-prompt.md": "JUDGE_PROMPT",
        }
        for relative, constant in templates.items():
            with self.subTest(file=relative):
                self.assertEqual((task / relative).read_text(), getattr(codegen_scaffold, constant))
        for destination, source in (("run_rewardkit.py", "codegen_rewardkit_runner.py"), ("reference_check.py", "codegen_reference_check.py")):
            self.assertEqual((task / "tests" / destination).read_bytes(), (SOURCE_ROOT / "src/expo_harbor_evals" / source).read_bytes())
        for source in (task / "solution/reference").rglob("*"):
            if source.is_file():
                self.assertEqual(source.read_bytes(), (task / "tests/reference" / source.relative_to(task / "solution/reference")).read_bytes())
        for relative in ("tests/test.sh", "solution/solve.sh"):
            self.assertTrue((task / relative).stat().st_mode & stat.S_IXUSR)

    @unittest.skipIf(TaskConfig is None, "Harbor is not installed in this Python environment")
    def test_export_parses_as_a_harbor_task(self):
        task = self.export()
        config = TaskConfig.model_validate(tomllib.loads((task / "task.toml").read_text()))
        self.assertEqual(config.schema_version, "1.3")
        self.assertEqual(config.environment.workdir, "/app")

    @unittest.skipIf(JudgeTomlConfig is None, "Rewardkit is not installed in this Python environment")
    def test_export_parses_as_a_rewardkit_rubric(self):
        task = self.export()
        rubric = JudgeTomlConfig.model_validate(tomllib.loads((task / "tests/requirements/rubric.toml").read_text()))
        self.assertEqual(len(rubric.criterion), len(self.draft["criteria"]))

    def test_baseline_manifest_matches_canonical_guard_with_vendored_dependencies(self):
        task = self.export()
        stored = json.loads((task / "tests/requirements/baseline-manifest.json").read_text())["files"]
        self.assertEqual(stored, submission_manifest(task / "environment"))
        self.assertEqual(set(stored), {"App.tsx", "src/state.ts", "package.json"})
        self.assertTrue((task / "environment/node_modules/fixture/index.js").is_file())
        self.assertIsNotNone(guard_reason(task / "tests/requirements", task / "environment"))

    def test_each_negative_control_keeps_its_own_failure_expectations(self):
        task = self.export()
        expectations = json.loads((task / "tests/requirements/calibration.json").read_text())
        self.assertEqual(expectations["baseline-comment"]["must_fail"], ["ready-state"])
        self.assertEqual(expectations["distractor"]["must_fail"], ["listener-cleanup"])
        for bracket, values, reward in (("baseline-comment", (0.0, 1.0), 0.75), ("distractor", (1.0, 0.0), 0.25)):
            with self.subTest(bracket=bracket):
                result = {"reward": reward, "guarded": False, "criteria": [
                    {"id": criterion["id"], "value": value}
                    for criterion, value in zip(self.draft["criteria"], values)
                ]}
                accepted, note = codegen_calibrate.assess_bracket(task, bracket, result)
                self.assertTrue(accepted, note)

    def test_export_never_overwrites_a_revision_or_edits_the_active_suite(self):
        active = self.root / "tasks/codegen/studio-control-regression/task.toml"
        active.parent.mkdir(parents=True)
        active.write_text("existing task\n")
        suite = self.root / "suites/mobile-v2.json"
        suite.parent.mkdir()
        suite.write_text('{"locked":true}\n')
        first = self.export()
        original = (first / "instruction.md").read_bytes()
        self.draft["instruction"] = "A changed prompt that must not overwrite the existing export."
        with self.assertRaisesRegex(ValueError, "already exported"):
            export_task.export_task(self.draft)
        self.assertEqual((first / "instruction.md").read_bytes(), original)
        self.draft["revision"] += 1
        second = self.export()
        self.assertNotEqual(first, second)
        self.assertEqual((first / "instruction.md").read_bytes(), original)
        self.assertEqual(active.read_text(), "existing task\n")
        self.assertEqual(suite.read_text(), '{"locked":true}\n')

    def test_export_rejects_parent_hidden_and_backslash_file_paths(self):
        for unsafe in ("../outside.txt", "src/../../outside.txt", ".env", "src/.secret", "src\\secret.ts"):
            with self.subTest(path=unsafe):
                draft = deepcopy(self.draft)
                draft["files"][0]["path"] = unsafe
                with self.assertRaises(ValueError):
                    export_task.export_task(draft)
                self.assertFalse((self.root / "outside.txt").exists())
                self.assertFalse(any((self.root / "outputs").rglob("instruction.md")))

    def test_export_rejects_escaping_identifiers_and_symlinked_output(self):
        for field, value in (("slug", "../outside"), ("id", "../../outside")):
            with self.subTest(field=field):
                draft = {**self.draft, field: value}
                with self.assertRaises(ValueError):
                    export_task.export_task(draft)
        with tempfile.TemporaryDirectory(prefix="studio-outside-test-") as outside:
            (self.root / "outputs").symlink_to(Path(outside).resolve(), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlinked"):
                export_task.export_task(self.draft)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_guard_checks_use_only_deterministic_providers(self):
        task = self.export()
        with patch.object(guards, "guard_reason", wraps=guards.guard_reason) as provider, \
                patch.object(guards, "write_guard_result", wraps=guards.write_guard_result) as writer, \
                patch.object(codegen_calibrate, "_run_verifier", side_effect=AssertionError("A guard check must not run a judge verifier")) as verifier:
            result = guards.check_guards(task)
        self.assertTrue(result["ok"])
        self.assertEqual([row["bracket"] for row in result["results"]], ["empty", "baseline"])
        self.assertTrue(all(row["ok"] and row["reward"] == 0 for row in result["results"]))
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(writer.call_count, 2)
        verifier.assert_not_called()

    def test_stale_baseline_fails_closed_without_judge_or_subprocess(self):
        task = self.export()
        (task / "environment/App.tsx").write_text("export const changedAfterManifest = true;\n")
        judge = types.ModuleType("rewardkit.runner")
        judge.run = Mock(side_effect=AssertionError("Paid judging must be unreachable"))
        with patch.dict(sys.modules, {"rewardkit.runner": judge}), \
                patch("subprocess.run", side_effect=AssertionError("No verifier subprocess is allowed")) as run, \
                patch("subprocess.Popen", side_effect=AssertionError("No verifier process is allowed")) as popen, \
                patch.object(codegen_calibrate, "_run_verifier", side_effect=AssertionError("No judge verifier is allowed")) as verifier, \
                patch.object(guards, "write_guard_result", wraps=guards.write_guard_result) as writer:
            result = guards.check_guards(task)
        self.assertFalse(result["ok"])
        empty, baseline = result["results"]
        self.assertTrue(empty["ok"])
        self.assertFalse(baseline["ok"])
        self.assertIsNone(baseline["reward"])
        self.assertIn("No judge was called", baseline["note"])
        self.assertEqual(writer.call_count, 1)
        judge.run.assert_not_called()
        run.assert_not_called()
        popen.assert_not_called()
        verifier.assert_not_called()

    def test_failed_guard_assessment_is_not_reported_as_a_success(self):
        task = self.export()
        with patch.object(guards, "assess_bracket", return_value=(False, "Invalid guard result")):
            result = guards.check_guards(task)
        self.assertFalse(result["ok"])
        self.assertTrue(all(not row["ok"] for row in result["results"]))
        self.assertTrue(all(row["note"] == "Invalid guard result" for row in result["results"]))


if __name__ == "__main__":
    unittest.main()
