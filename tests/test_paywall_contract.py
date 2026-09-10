"""Exercise authored paywall controls locally, without a judge or native runtime."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TASK = Path(__file__).resolve().parents[1] / "tasks/codegen/feedback-11-anonymous-paywall-eligibility"


@pytest.mark.parametrize("control,failures", [
    ("environment", ["anonymous-and-identified-eligibility"]),
    ("solution/reference", []),
    ("solution/reference-alternative", []),
    ("solution/distractor", ["anonymous-and-identified-eligibility", "placement-specific-offering", "resource-and-entitlement-gates"]),
])
def test_paywall_control_truth_table(control, failures):
    node = shutil.which("node")
    assert node, "Node.js is required for the offline paywall contract checks"
    result = subprocess.run([node, str(TASK / "tests/contract.cjs"), str(TASK / control / "paywall.js")],
                            check=True, capture_output=True, text=True, timeout=20)
    report = json.loads(result.stdout)
    assert report["checks"] == 4860
    assert report["failedGroups"] == failures
