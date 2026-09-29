import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import catalog


class CatalogBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-catalog-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "repository"
        self.root.mkdir()
        self.root_patch = patch.object(catalog, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def trial(self, run="sample", name="attempt"):
        trial = self.root / "runs" / run / name
        self.write_json(trial / "result.json", {
            "task_name": "example-task", "agent_info": {"name": "nop"},
            "verifier_result": {"rewards": {"reward": 0}},
        })
        return trial

    def test_canonical_nested_json_reads_reject_symlinks(self):
        private = self.write_json(self.base / "private.json", {
            "sentinel": "outside repository", "reward": {"criteria": []},
        })
        original_reader = catalog.report.read_json
        for index, relative in enumerate((
            "evaluation.json", "verifier/details.json", "verifier/reward-details.json",
        )):
            with self.subTest(relative=relative):
                trial = self.trial(run=f"unsafe-{index}")
                link = trial / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(private)
        self.trial(run="valid")
        trials, warnings = catalog.all_trials()
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].source_dir.parent.name, "valid")
        self.assertEqual(len(warnings), 3)
        self.assertTrue(all("Symlinked paths" in warning for warning in warnings))
        self.assertIs(catalog.report.read_json, original_reader)

    def test_canonical_reader_rejects_symlinked_metadata_directory(self):
        trial = self.trial()
        outside = self.base / "private-verifier"
        self.write_json(outside / "details.json", {"backend": "outside repository"})
        (trial / "verifier").symlink_to(outside, target_is_directory=True)
        trials, warnings = catalog.all_trials()
        self.assertEqual(trials, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Symlinked paths", warnings[0])

    def test_run_discovery_rejects_symlinked_results_without_losing_other_runs(self):
        trial = self.trial(run="unsafe")
        original = trial / "result.json"
        external = self.base / "private.json"
        original.rename(external)
        original.symlink_to(external)
        self.trial(run="valid")
        trials, warnings = catalog.all_trials()
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].source_dir.parent.name, "valid")
        self.assertEqual(len(warnings), 1)

    def test_task_calibration_uses_the_same_read_boundary(self):
        task = self.root / "tasks/codegen/example-task"
        requirements = task / "tests/requirements"
        requirements.mkdir(parents=True)
        (task / "task.toml").write_text('[task]\ndescription = "Example"\n[metadata]\nfamily = "expo-codegen"\n')
        (task / "instruction.md").write_text("Example task")
        private = self.write_json(self.base / "private.json", {"sentinel": "outside repository"})
        (requirements / "calibration.json").symlink_to(private)
        with self.assertRaisesRegex(ValueError, "Symlinked paths"):
            catalog.task_record(task, detail=True)

    def test_symlinked_runs_root_is_rejected(self):
        outside = self.base / "outside-runs"
        outside.mkdir()
        (self.root / "runs").symlink_to(outside, target_is_directory=True)
        trials, warnings = catalog.all_trials()
        self.assertEqual(trials, [])
        self.assertEqual(len(warnings), 1)

    def native_result(self, directory, *, passed=False):
        checks = [{"name": "candidate-build", "passed": True}]
        checks += ([{"name": name, "passed": True} for name in (
            "picker-cancel-0", "picker-cancel-1", "successful-image-selection-renders",
        )] if passed else [{"name": "native-ui", "passed": False}])
        self.write_json(directory / "details.json", {
            "kind": "native-ui", "task": "example-task", "backend": "local-macos",
            "status": "passed" if passed else "failed", "checks": checks, "errors": [],
            "input": {"profile": "picker"},
        })

    def test_native_calibration_is_loaded_once_with_control_identity(self):
        root = self.root / "runs/native-controls"
        self.write_json(root / "calibration.json", {"kind": "native-scenario-calibration"})
        self.native_result(root / "baseline-1/evaluation")
        self.native_result(root / "reference-1/evaluation", passed=True)
        trials, warnings = catalog.all_trials()
        self.assertEqual(warnings, [])
        self.assertEqual(len(trials), 2)
        rows = {trial.name: trial for trial in trials}
        self.assertEqual(set(rows), {"baseline-1", "reference-1"})
        self.assertTrue(all(trial.agent == "calibration-control" for trial in trials))
        self.assertEqual(rows["baseline-1"].model, "Control: baseline")
        self.assertEqual(rows["baseline-1"].outcome, "fail")
        self.assertEqual(rows["reference-1"].outcome, "pass")

    def test_native_artifacts_include_owned_screens_and_logs(self):
        directory = self.root / "runs/native-candidate/evidence/native-eval"
        self.native_result(directory)
        self.write_json(directory / "screens/001.json", {"nodes": []})
        (directory / "screens/failure.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (directory / "logs").mkdir()
        (directory / "logs/build.log").write_text("Build completed")
        (directory / "logs/.env").write_text("hidden")
        private = self.write_json(self.base / "private.json", {"sentinel": "outside repository"})
        (directory / "logs/private.json").symlink_to(private)
        trials, warnings = catalog.all_trials()
        self.assertEqual(warnings, [])
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].agent, "submitted-app")
        paths = {str(path.relative_to(directory)) for path in catalog.artifact_paths(trials[0])}
        self.assertEqual(paths, {"details.json", "screens/001.json", "screens/failure.png", "logs/build.log"})
        image = catalog.file_content(directory, "screens/failure.png")
        self.assertEqual(image["kind"], "image")
        self.assertTrue(image["content"].startswith("data:image/png;base64,"))
        with self.assertRaisesRegex(ValueError, "Symlinked paths"):
            catalog.file_content(directory, "logs/private.json")


if __name__ == "__main__":
    unittest.main()
