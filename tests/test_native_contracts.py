"""Validate new control fixtures without a model, native build, or simulator."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("kind,control,failures", [
    ("layout", "environment", ["native-fixed-column", "responsive-content-fit"]),
    ("layout", "reference", []),
    ("layout", "reference-alternative", []),
    ("layout", "distractor", ["native-fixed-column", "responsive-content-fit"]),
    ("auth", "environment", ["fixed-outer-field-height", "rendered-authentication-path"]),
    ("auth", "reference", []),
    ("auth", "reference-alternative", []),
    ("auth", "distractor", ["fixed-outer-field-height", "rendered-authentication-path", "settings-and-native-controls-preserved"]),
])
def test_authored_render_controls(kind, control, failures):
    assert (ROOT / "tests/contracts/node_modules/esbuild").exists(), "Run npm ci --prefix tests/contracts once before make test"
    result = subprocess.run(["node", str(ROOT / "tests/contracts/run-controls.mjs"), kind, control],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["failedGroups"] == failures
    assert len(report["evidence"]) == (8 if kind == "layout" else 2)
    if kind == "layout":
        assert all(case["webDefaultsAmountWidth"] == 112 for case in report["evidence"])
