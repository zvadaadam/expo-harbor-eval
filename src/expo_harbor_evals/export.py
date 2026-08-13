"""Append finished runs' summaries to a git-tracked history file.

supabase/evals-style results-over-time: each finished Harbor run exports one
JSONL row (run name, finish time, per-configuration means) into
results/history.jsonl, deduplicated on (run, finished_at). The viewer renders
the accumulated history so regressions across model/tool/prompt changes are
visible, not just point-in-time reports.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from expo_harbor_evals.report import build_series, group_tasks, load_runs, series_stats

DEFAULT_HISTORY = Path("results/history.jsonl")


def summarize_run(run_dir: Path) -> dict | None:
    job, trials = load_runs([run_dir])
    if not trials or not job.get("finished_at"):
        return None
    tasks = group_tasks(trials)
    series = build_series(trials)
    rows = []
    for entry in series:
        stat = series_stats(tasks, entry.key)
        rows.append(
            {
                "key": entry.key,
                "label": entry.label,
                "mean": round(stat.mean, 4) if stat.mean is not None else None,
                "solved": stat.solved,
                "n_tasks": stat.n_tasks,
                "mean_cost_usd": round(stat.mean_cost, 4)
                if stat.mean_cost is not None
                else None,
                "total_cost_usd": round(stat.total_cost, 4)
                if stat.total_cost is not None
                else None,
                "n_input_tokens": stat.input_tokens,
                "n_cache_tokens": stat.cache_tokens,
                "n_output_tokens": stat.output_tokens,
            }
        )
    costs = [t.cost_usd for t in trials if t.cost_usd is not None]
    return {
        "run": run_dir.name,
        "finished_at": job["finished_at"],
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_trials": len(trials),
        "n_tasks": len(tasks),
        # Agent-side claude CLI spend for the whole run; judge spend is not
        # reported by harbor-rewardkit and is not included.
        "total_cost_usd": round(sum(costs), 4) if costs else None,
        "series": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        type=Path,
        nargs="*",
        help="Run directories to export; defaults to every finished run under runs/",
    )
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    args = parser.parse_args()

    run_dirs = args.run_dirs or sorted(
        d for d in Path("runs").iterdir() if (d / "result.json").exists()
    )

    seen: set[tuple[str, str]] = set()
    existing: list[str] = []
    if args.history.exists():
        for line in args.history.read_text().splitlines():
            if not line.strip():
                continue
            existing.append(line)
            try:
                row = json.loads(line)
                seen.add((row.get("run"), row.get("finished_at")))
            except ValueError:
                continue

    appended = 0
    lines = list(existing)
    for run_dir in run_dirs:
        summary = summarize_run(run_dir)
        if summary is None:
            print(f"skip {run_dir.name}: unfinished or empty")
            continue
        dedup_key = (summary["run"], summary["finished_at"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        lines.append(json.dumps(summary))
        appended += 1

    args.history.parent.mkdir(parents=True, exist_ok=True)
    args.history.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"history: {len(lines)} rows ({appended} appended) -> {args.history}")


if __name__ == "__main__":
    main()
