"""Calibrate every expo-codegen task's scoring brackets.

Three brackets per task, all of which must hold before a model number means
anything (CONTRIBUTING.md, "Calibration is mandatory"):

- empty workspace      -> 0.0 via the deterministic guard, no judge call;
- unchanged baseline   -> 0.0 via the deterministic guard, no judge call;
- reference solution   -> 1.0 from the real judge.

Tasks that ship a `solution/distractor/` — a plausible-but-wrong fix, ideally
one a field report tested and found insufficient — get a fourth bracket:

- distractor solution  -> below 1.0 from the real judge.

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
import shutil
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from expo_harbor_evals.codegen_rewardkit_runner import SCAFFOLDING_FILES

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
    dirs = [
        toml.parent
        for toml in sorted(tasks_root.glob("*/task.toml"))
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


def _run_verifier(task_dir: Path, workspace: Path, output: Path) -> dict:
    completed = subprocess.run(
        [
            "uv",
            "run",
            str(task_dir / "tests" / "run_rewardkit.py"),
            str(task_dir / "tests" / "requirements"),
            str(workspace),
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(
            f"verifier failed for {task_dir.name}: {completed.stderr[-500:]}"
        )
    reward = json.loads(output.read_text())["reward"]
    details_path = output.parent / "reward-details.json"
    guarded = False
    if details_path.exists():
        guarded = "guard" in json.loads(details_path.read_text()).get("reward", {})
    return {"reward": reward, "guarded": guarded}


def _bracket(
    task_dir: Path, bracket: str, scratch: Path
) -> BracketResult:
    workspace = scratch / task_dir.name / bracket / "app"
    output = scratch / task_dir.name / bracket / "reward.json"
    workspace.mkdir(parents=True)
    if bracket in ("baseline", "reference", "distractor"):
        _copy_environment(task_dir / "environment", workspace)
    if bracket in ("reference", "distractor"):
        shutil.copytree(
            task_dir / "solution" / bracket, workspace, dirs_exist_ok=True
        )
    try:
        result = _run_verifier(task_dir, workspace, output)
    except RuntimeError as error:
        return BracketResult(task_dir.name, bracket, None, False, False, str(error))

    reward, guarded = result["reward"], result["guarded"]
    if bracket == "reference":
        ok = reward == 1.0 and not guarded
        note = "" if ok else "reference must judge to 1.0"
    elif bracket == "distractor":
        ok = reward < 1.0 and not guarded
        note = "" if ok else "distractor must judge below 1.0"
    else:
        ok = reward == 0.0 and guarded
        note = "" if ok else "must guard to 0.0 without a judge call"
    return BracketResult(task_dir.name, bracket, reward, guarded, ok, note)


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
    args = parser.parse_args()

    task_dirs = codegen_task_dirs(args.tasks)
    if args.only:
        wanted = set(args.only)
        task_dirs = [d for d in task_dirs if d.name in wanted]
        if missing := wanted - {d.name for d in task_dirs}:
            raise SystemExit(f"Unknown task(s): {', '.join(sorted(missing))}")
    judged: list[tuple[Path, str]] = []
    if not args.guards_only:
        for task_dir in task_dirs:
            judged.append((task_dir, "reference"))
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
                results.append(_bracket(task_dir, bracket, scratch))
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
                        lambda pair: _bracket(pair[0], pair[1], scratch),
                        judged,
                    )
                )

    failures = [result for result in results if not result.ok]
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
