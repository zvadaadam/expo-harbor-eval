"""Check canonical deterministic guards without any judge execution path."""
import json
from pathlib import Path
import sys
import tempfile

from catalog import ROOT, contained, task_dir
from expo_harbor_evals.codegen_calibrate import _copy_environment, assess_bracket
from expo_harbor_evals.codegen_rewardkit_runner import guard_reason, write_guard_result


def check_guards(task: Path) -> dict:
    rows = []
    with tempfile.TemporaryDirectory(prefix="studio-guards-") as temporary:
        for bracket in ("empty", "baseline"):
            workspace = Path(temporary) / bracket / "app"
            workspace.mkdir(parents=True)
            if bracket == "baseline":
                _copy_environment(task / "environment", workspace)
            reason = guard_reason(task / "tests/requirements", workspace)
            if reason is None:
                rows.append({"bracket": bracket, "ok": False, "reward": None,
                             "note": "Guard did not reject this control. No judge was called; check the baseline manifest."})
                continue
            write_guard_result(task / "tests/requirements", Path(temporary) / bracket / "reward.json", reason)
            ok, note = assess_bracket(task, bracket, {"reward": 0.0, "guarded": True})
            rows.append({"bracket": bracket, "ok": ok, "reward": 0.0, "note": reason if ok else note})
    return {"scope": "guards-only", "ok": all(row["ok"] for row in rows), "results": rows}


if __name__ == "__main__":
    result = check_guards(task_dir(sys.argv[1]))
    output = contained(ROOT, Path(sys.argv[2]))
    output.write_text(json.dumps(result, indent=2) + "\n")
    for row in result["results"]:
        print(f"{row['bracket']}: {'PASS' if row['ok'] else 'FAIL'} — {row['note']}")
    print("\nNo model or judge calls were made.")
    sys.exit(0 if result["ok"] else 1)
