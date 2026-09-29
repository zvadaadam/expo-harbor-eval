"""Calibrate every expo-codegen task's scoring brackets.

Four brackets per task, all of which must hold before a model number means
anything (CONTRIBUTING.md, "Calibration is mandatory"):

- empty workspace      -> 0.0 via the deterministic guard, no judge call;
- unchanged baseline   -> 0.0 via the deterministic guard, no judge call;
- reference solution   -> 1.0 from the real judge.
- commented baseline   -> the declared missing behaviors fail the real judge.

Tasks that ship a `solution/distractor/` — a plausible-but-wrong fix, ideally
one a field report tested and found insufficient — get another bracket:

- distractor solution  -> its declared broken behaviors fail the real judge.

Alternative valid references, when supplied, must also pass every criterion.

Reference alone proves the judge rewards the right answer; the distractor
proves it can tell the right answer from a convincing wrong one.

The judged brackets need credentials exactly like `make codegen-judge`
(REWARDKIT_JUDGE=claude-code for the logged-in CLI, or a LiteLLM id plus
provider key). Pass --guards-only to skip them, or --only <task-dir-name>
to calibrate a single task while authoring it.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from expo_harbor_evals.codegen_rewardkit_runner import SCAFFOLDING_FILES, behavior_spec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class BracketResult:
    task: str
    bracket: str
    reward: float | None
    guarded: bool
    ok: bool
    note: str = ""


def codegen_task_dirs(tasks_root: Path) -> list[Path]:
    """Find family members by metadata at any depth, so folder layout is free
    to group tasks (tasks/codegen/ today) without touching discovery."""
    dirs = [
        toml.parent
        for toml in sorted(tasks_root.rglob("task.toml"))
        if tomllib.loads(toml.read_text())["metadata"].get("family")
        == "expo-codegen"
    ]
    if not dirs:
        raise SystemExit(f"No expo-codegen tasks found under {tasks_root}")
    return dirs


def _copy_environment(environment: Path, workspace: Path) -> None:
    for child in environment.iterdir():
        if child.name in SCAFFOLDING_FILES or child.name.startswith("."):
            continue
        if child.is_dir():
            shutil.copytree(child, workspace / child.name)
        else:
            shutil.copy2(child, workspace / child.name)


def _run_verifier(task_dir: Path, workspace: Path, output: Path, behavior_only: bool = False) -> dict:
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(task_dir / "tests" / "run_rewardkit.py"),
            str(task_dir / "tests" / "requirements"),
            str(workspace),
            str(output),
            *(["--behavior-only"] if behavior_only else []),
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(
            f"verifier failed for {task_dir.name}: {completed.stderr[-500:]}"
        )
    reward = json.loads(output.read_text())["reward"]
    details_path = output.parent / "reward-details.json"
    details = {}
    if details_path.exists():
        details = json.loads(details_path.read_text()).get("reward", {})
    return {"reward": reward, "guarded": "guard" in details,
            "criteria": details.get("criteria", []), "behavior_only": behavior_only,
            "source_review_skipped": details.get("source_review_skipped")}


def assess_bracket(task_dir: Path, bracket: str, result: dict) -> tuple[bool, str]:
    """A negative control must fail the behavior deliberately broken by it."""
    reward, guarded = result["reward"], result["guarded"]
    rubric = tomllib.loads((task_dir / "tests/requirements/rubric.toml").read_text())
    aggregation = rubric.get('scoring', {}).get('aggregation', 'weighted-mean').replace('_', '-')
    if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward) or (aggregation != 'weighted-sum' and not 0 <= reward <= 1):
        return False, "invalid reward"
    if bracket in ("empty", "baseline"):
        return (reward == 0 and guarded), "must guard to 0 without a judge call"
    behavior = behavior_spec(task_dir / "tests/requirements")
    if result.get("behavior_only") or result.get("source_review_skipped"):
        if behavior is None:
            return False, "no declared behavioral contract"
        rubric["criterion"] = [c for c in rubric["criterion"] if c["id"] in behavior["criteria"]]
    expected_ids = {c["id"] for c in rubric["criterion"]}
    rows = result.get("criteria", [])
    if not isinstance(rows, list) or any(not isinstance(c, dict) for c in rows):
        return False, "judge criteria must be a list of results"
    if any(c.get("error") for c in rows):
        return False, "judge errors cannot establish calibration"
    if any(not isinstance(c.get("id", c.get("name")), str) for c in rows):
        return False, "judge criterion IDs must be strings"
    values = {c.get("id", c.get("name")): c.get("value") for c in rows}
    if result.get("source_review_skipped") and not any(value == 0 for value in values.values()):
        return False, "source review can only be skipped for a failed required policy"
    if guarded or set(values) != expected_ids or len(rows) != len(expected_ids):
        return False, "judge must return each declared criterion exactly once"
    for criterion in rubric['criterion']:
        value = values[criterion['id']]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            return False, 'criteria must contain finite normalized scores from 0 to 1'
        if criterion.get('type', 'binary') == 'binary' and value not in (0, 1):
            return False, 'binary criteria must contain numeric 0 or 1'
    from rewardkit.models import Score
    from rewardkit.reward import aggregate_scores
    expected_reward = aggregate_scores([Score(name=c['id'], value=values[c['id']], raw=values[c['id']], weight=c['weight'], optional=c.get('optional', False)) for c in rubric['criterion']], aggregation, rubric.get('scoring', {}).get('threshold', 0.5))
    if behavior is not None:
        expected_reward = float(all(values.values()))
    # Rewardkit serializes the aggregate to four decimal places.
    if not math.isclose(reward, round(expected_reward, 4), abs_tol=1e-6):
        return False, "aggregate reward disagrees with criterion results"
    maximum = sum(max(0, c['weight']) for c in rubric['criterion']) if aggregation == 'weighted-sum' else 1
    ideal = {c['id']: 0 if aggregation == 'weighted-sum' and c['weight'] < 0 else 1 for c in rubric['criterion']}
    if bracket.startswith("reference"):
        return math.isclose(reward, round(maximum, 4), abs_tol=1e-6) and all(values[key] == value for key, value in ideal.items()), "every reference criterion must achieve its ideal score"
    spec = json.loads((task_dir / "tests/requirements/calibration.json").read_text())
    required_failures = spec[bracket]["must_fail"]
    if not required_failures or not set(required_failures) <= expected_ids:
        return False, "invalid negative-control criterion IDs"
    return (reward < maximum and all(values[key] == 1 - ideal[key] for key in required_failures)), \
        "must fail: " + ", ".join(required_failures)


def _bracket(
    task_dir: Path, bracket: str, scratch: Path, behavior_only: bool = False,
) -> BracketResult:
    workspace = scratch / task_dir.name / bracket / "app"
    output = scratch / task_dir.name / bracket / "reward.json"
    workspace.mkdir(parents=True)
    if bracket != "empty":
        _copy_environment(task_dir / "environment", workspace)
    if bracket.startswith("reference") or bracket == "distractor":
        shutil.copytree(
            task_dir / "solution" / bracket, workspace, dirs_exist_ok=True
        )
    if bracket == "baseline-comment":
        # Legal comment changes bytes, not program behavior. The real judge
        # must now reject the missing behavior rather than relying on the guard.
        source = next(iter(sorted(workspace.rglob("*.tsx"))), None)
        if source is None:
            raise ValueError(f"No TSX entry for negative control: {task_dir.name}")
        source.write_text(source.read_text() + "\n// Calibration: unchanged behavior.\n")
    try:
        result = _run_verifier(task_dir, workspace, output, behavior_only)
        ok, note = assess_bracket(task_dir, bracket, result)
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        return BracketResult(task_dir.name, bracket, None, False, False, str(error))

    reward, guarded = result["reward"], result["guarded"]
    return BracketResult(task_dir.name, bracket, reward, guarded, ok, "" if ok else note)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=REPO_ROOT / "tasks")
    parser.add_argument(
        "--guards-only",
        action="store_true",
        help="Skip the judged brackets (no credentials needed).",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="TASK",
        help="Calibrate only the named task directory (repeatable).",
    )
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--behavior-only", action="store_true", help="Calibrate declared policy contracts without a source judge")
    parser.add_argument("--output", type=Path, help="Save machine-readable bracket results")
    args = parser.parse_args()

    task_dirs = codegen_task_dirs(args.tasks)
    if args.behavior_only:
        task_dirs = [task for task in task_dirs if behavior_spec(task / "tests/requirements")]
        if not task_dirs:
            parser.error("No tasks with behavioral contracts")
    if args.only:
        wanted = set(args.only)
        task_dirs = [d for d in task_dirs if d.name in wanted]
        if missing := wanted - {d.name for d in task_dirs}:
            raise SystemExit(f"Unknown task(s): {', '.join(sorted(missing))}")
    judged: list[tuple[Path, str]] = []
    if not args.guards_only:
        for task_dir in task_dirs:
            judged.append((task_dir, "reference"))
            judged.append((task_dir, "baseline-comment"))
            if (task_dir / "solution/reference-alternative").is_dir():
                judged.append((task_dir, "reference-alternative"))
            if (task_dir / "solution" / "distractor").is_dir():
                judged.append((task_dir, "distractor"))
    results: list[BracketResult] = []
    with tempfile.TemporaryDirectory(prefix="codegen-calibrate-") as scratch_str:
        scratch = Path(scratch_str)
        # Guard brackets are cheap and deterministic; run them serially first
        # and skip the judged brackets entirely if any guard fails, so a
        # broken guard costs no judge spend.
        for task_dir in task_dirs:
            for bracket in ("empty", "baseline"):
                results.append(_bracket(task_dir, bracket, scratch, args.behavior_only))
        if judged and any(not result.ok for result in results):
            print(
                "Guard bracket violation(s) — skipping judged brackets.",
                file=sys.stderr,
            )
            judged = []
        if judged:
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                results.extend(
                    pool.map(
                        lambda pair: _bracket(pair[0], pair[1], scratch, args.behavior_only),
                        judged,
                    )
                )

    failures = [result for result in results if not result.ok]
    if args.output:
        from dataclasses import asdict
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"ok": not failures,
            "scope": "guards-only" if args.guards_only else "policy-behavior-calibration" if args.behavior_only else "source-judge-calibration",
            "results": [asdict(result) for result in results]}, indent=2) + "\n")
    by_task: dict[str, list[BracketResult]] = {}
    for result in results:
        by_task.setdefault(result.task, []).append(result)
    for task, rows in by_task.items():
        cells = "  ".join(
            f"{row.bracket}={row.reward if row.reward is not None else 'error'}"
            f"{'✓' if row.ok else '✗'}"
            for row in rows
        )
        print(f"{task}: {cells}")
    if failures:
        print(f"\n{len(failures)} calibration violation(s):", file=sys.stderr)
        for failure in failures:
            print(
                f"  {failure.task} [{failure.bracket}] "
                f"reward={failure.reward} {failure.note}",
                file=sys.stderr,
            )
        raise SystemExit(1)
    print(f"\nAll {len(results)} brackets hold across {len(by_task)} tasks.")


if __name__ == "__main__":
    main()
