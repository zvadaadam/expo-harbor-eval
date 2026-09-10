"""Render a self-contained HTML report from one or more Harbor run directories.

Reads each trial's result.json plus verifier/reward-details.json and emits a
single HTML file with separate measurement views, an outcome matrix and
expandable native/source evidence. Configurations retain their model, backend and experiment identity, so baseline/oracle runs and model/effort ladders can
be merged into one report:

    uv run expo-eval-report runs/codegen-judge runs/codegen-models

Stdlib only, so it runs anywhere the repo does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# Categorical palette slots 1-8 (light, dark), assigned to series in display
# order. Ordering within the palette is the CVD-safety mechanism; do not
# shuffle. See the repo report for provenance.
PALETTE = [
    ("#2a78d6", "#3987e5"),
    ("#1baf7a", "#199e70"),
    ("#eda100", "#c98500"),
    ("#008300", "#008300"),
    ("#4a3aa7", "#9085e9"),
    ("#e34948", "#e66767"),
    ("#e87ba4", "#d55181"),
    ("#eb6834", "#d95926"),
]

MODEL_ORDER = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
EFFORT_ORDER = {"": 1, "low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}


@dataclass
class Trial:
    name: str
    task: str
    agent: str
    model: str
    reward: float | None
    criteria: list[dict]
    judge: dict
    error: str | None
    cost_usd: float | None
    input_tokens: int | None
    cache_tokens: int | None
    output_tokens: int | None
    backend: str = ""
    measurement: str = ""
    experiment: str = ""
    checks: list[dict] = field(default_factory=list)
    source_dir: Path | None = None
    run: str = ""
    planned_tasks: tuple[str, ...] = ()
    planned_attempts: int | None = None
    pending: bool = False
    provenance: dict = field(default_factory=dict)

    @property
    def outcome(self) -> str:
        if self.pending:
            return "pending"
        if self.error or self.reward is None:
            return "error"
        return "pass" if self.reward == 1 else "fail" if self.reward == 0 else "partial"

    @property
    def series_key(self) -> str:
        base = f"{self.agent}|{self.model}"
        base = f"{base}|{self.backend}" if self.backend else base
        if self.measurement or self.experiment:
            base += f"|{self.measurement}|{self.experiment}"
        return base


@dataclass
class Series:
    key: str
    label: str
    rank: tuple
    css: str = ""
    light: str = "#898781"
    dark: str = "#898781"


@dataclass
class TaskRow:
    """Trials grouped per series; each cell holds every attempt."""

    name: str
    by_series: dict[str, list[Trial]] = field(default_factory=dict)

    def cell_rewards(self, key: str) -> list[float]:
        return [
            t.reward for t in self.by_series.get(key, []) if t.reward is not None and not t.error
        ]

    def cell_mean(self, key: str) -> float | None:
        return mean(self.cell_rewards(key))


def _series_for(agent: str, model: str) -> Series:
    if agent == "nop":
        return Series(key=f"{agent}|{model}", label="Baseline (no-op)", rank=(0,))
    if agent == "oracle":
        if model == "out-of-order":
            return Series(key=f"{agent}|{model}", label="Oracle (wrong order)", rank=(8,))
        return Series(key=f"{agent}|{model}", label="Oracle (reference)", rank=(9,))
    # model may carry a "#tag" variant (e.g. the driver tool: "sonnet#argent")
    # and an "@effort" suffix; both flow into the label and ordering.
    base, _, tool = model.partition("#")
    name, _, effort = base.partition("@")
    name = name or agent
    label = name
    if effort:
        label += f" · {effort} effort"
    if tool:
        label += f" × {tool}"
    rank = (1, MODEL_ORDER.get(name, 8), EFFORT_ORDER.get(effort, 1), tool, label)
    return Series(key=f"{agent}|{model}", label=label, rank=rank)


def series_for(agent: str, model: str, backend: str = "") -> Series:
    series = _series_for(agent, model)
    if backend:
        series.key += f"|{backend}"
        series.label += f" · {backend}"
    return series


def read_json(path: Path) -> dict | list | None:
    """Read JSON, returning None for missing, torn, or mid-write files."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_runs(run_dirs: list[Path]) -> tuple[dict, list[Trial]]:
    job: dict = {}
    trials: list[Trial] = []
    seen: set[Path] = set()
    for run_dir in run_dirs:
        run_dir = run_dir.resolve()
        current_job = read_json(run_dir / "result.json") or {}
        if not job:
            job = current_job
        config = read_json(run_dir / "config.json") or {}
        datasets = config.get("datasets", [])
        planned = tuple(sorted({name for d in datasets for name in d.get("task_names") or []}))
        # Sampling, exclusions and wildcard selectors do not enumerate a full
        # cohort. Keep their denominator unknown rather than guessing it.
        if config.get("tasks") or any(
            not d.get("task_names") or d.get("n_tasks") is not None or d.get("exclude_task_names")
            or any(char in name for name in d.get("task_names", []) for char in "*?[")
            for d in datasets
        ):
            planned = ()
        # Harbor omits default values when serializing JobConfig; the pinned
        # runner's default is one attempt. Absent config is still unknown.
        attempts = config.get("n_attempts", 1 if config.get("agents") and config.get("datasets") else None)
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            attempts = None
        for trial_result in sorted(set(run_dir.glob("*/result.json")) | set(run_dir.glob("*/config.json"))):
            if trial_result.parent in seen:
                continue
            if trial_result.name == "config.json" and (trial_result.parent / "result.json").exists():
                continue
            raw = read_json(trial_result)
            if not isinstance(raw, dict):
                continue
            pending = trial_result.name == "config.json"
            if pending:
                task_config = raw.get("task") or {}
                agent_config = raw.get("agent") or {}
                host_names = {"expo_harbor_evals.claude_host_agent:ClaudeHostAgent": "claude-host",
                              "expo_harbor_evals.muse_host_agent:MuseHostAgent": "muse-host"}
                raw = {"task_name": Path(task_config.get("path") or "unknown").name,
                       "agent_info": {"name": agent_config.get("name") or host_names.get(agent_config.get("import_path")) or "unknown",
                                      "model_info": {"name": agent_config.get("model_name") or ""}}}
            elif not any(k in raw for k in ("agent_info", "verifier_result", "exception_info", "task_name")):
                continue
            seen.add(trial_result.parent)
            verifier_result = raw.get("verifier_result") or {}
            rewards = verifier_result.get("rewards") or {}
            exception = raw.get("exception_info") or None
            if pending and current_job.get("finished_at"):
                pending = False
                exception = "Finished run has no result for this started trial"
            if isinstance(exception, dict):
                exception = exception.get("exception_message") or str(exception)
            runner_ok = rewards.get("sim_runner_ok", rewards.get("mobile_runner_ok"))
            if runner_ok == 0:
                exception = exception or "Infrastructure failure: evidence/producer unavailable"
            sim_details = read_json(trial_result.parent / "verifier/details.json") or {}
            if not isinstance(sim_details, dict):
                sim_details = {}
            backend = sim_details.get("backend") or (sim_details.get("manifest") or {}).get("backend", "")
            identity = read_json(trial_result.parent / "evaluation.json") or {}
            backend = backend or identity.get("backend", "")

            criteria: list[dict] = []
            judge: dict = {}
            details = read_json(
                trial_result.parent / "verifier" / "reward-details.json"
            )
            if isinstance(details, dict):
                reward_details = details.get("reward")
                if isinstance(reward_details, dict):
                    criteria = reward_details.get("criteria") or []
                    judge = reward_details.get("judge") or {}

            agent_info = raw.get("agent_info") or {}
            model_info = agent_info.get("model_info") or {}
            agent_result = raw.get("agent_result") or {}
            task_name = raw.get("task_name") or raw.get("trial_name") or "unknown"
            trials.append(
                Trial(
                    name=trial_result.parent.name,
                    task=task_name.split("/")[-1],
                    agent=agent_info.get("name") or "unknown",
                    model=model_info.get("name") or "",
                    reward=None if runner_ok == 0 else rewards.get("reward"),
                    criteria=criteria,
                    judge=judge,
                    error=exception,
                    cost_usd=agent_result.get("cost_usd"),
                    input_tokens=agent_result.get("n_input_tokens"),
                    cache_tokens=agent_result.get("n_cache_tokens"),
                    output_tokens=agent_result.get("n_output_tokens"),
                    backend=backend,
                    measurement=identity.get("measurement", ""),
                    experiment=identity.get("experiment_sha256", ""),
                    checks=sim_details.get("checks") or [],
                    source_dir=trial_result.parent,
                    run=str(run_dir),
                    planned_tasks=planned,
                    planned_attempts=attempts,
                    pending=pending,
                    provenance=identity,
                )
            )
        # Standalone native verification and downloaded EAS candidate evidence
        # have details.json, not a fabricated Harbor agent result envelope.
        native_paths = {run_dir / "details.json", run_dir / "evidence/native-eval/details.json"}
        native_paths.update(run_dir.glob("*/details.json"))
        native_paths.update(run_dir.glob("*/evaluation/details.json"))
        calibration = read_json(run_dir / "calibration.json") or {}
        for path in sorted(native_paths):
            raw = read_json(path)
            if path.parent in seen or not isinstance(raw, dict) or raw.get("kind") != "native-ui":
                continue
            seen.add(path.parent)
            from expo_harbor_evals.mobile_scenarios import validate_result
            error = None
            try:
                validate_result(raw)
            except (ValueError, KeyError, TypeError) as exc:
                error = f"Invalid native evidence: {exc}"
            if raw.get("status") == "infra-error":
                error = "; ".join(raw.get("errors") or ["Native infrastructure failure"])
            spec = raw.get("input") or {}
            stable = {k: v for k, v in spec.items() if k != "trial_id"}
            identity = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
            control = calibration.get("kind") == "native-scenario-calibration" and path.parent.name == "evaluation"
            name = path.parent.parent.name if control else raw.get("trial_id") or path.parent.name
            model = f"Control: {name.rsplit('-', 1)[0]}" if control else f"Candidate {identity[:8]}"
            trials.append(Trial(name=name,
                task=raw.get("task") or "unknown", agent="calibration-control" if control else "submitted-app",
                model=model, reward=None if error else float(raw.get("status") == "passed"),
                criteria=[], judge={}, error=error, cost_usd=None, input_tokens=None, cache_tokens=None,
                output_tokens=None, backend=raw.get("backend") or "unknown",
                measurement="native-ui", experiment=identity, checks=raw.get("checks") or [],
                source_dir=path.parent, run=run_dir.name, provenance=spec))
    return job, trials


def build_series(trials: list[Trial]) -> list[Series]:
    by_key: dict[str, Series] = {}
    for trial in trials:
        if trial.series_key not in by_key:
            series = series_for(trial.agent, trial.model, trial.backend)
            series.key = trial.series_key
            if trial.experiment:
                series.label += f" · {trial.measurement} · {trial.experiment[:8]}"
            by_key[trial.series_key] = series
    ordered = sorted(by_key.values(), key=lambda s: s.rank)
    for index, series in enumerate(ordered):
        series.css = f"s-{index}"
        series.light, series.dark = PALETTE[index % len(PALETTE)]
    return ordered


def group_tasks(trials: list[Trial]) -> list[TaskRow]:
    rows: dict[str, TaskRow] = {}
    for trial in trials:
        row = rows.setdefault(trial.task, TaskRow(name=trial.task))
        row.by_series.setdefault(trial.series_key, []).append(trial)
    return [rows[name] for name in sorted(rows)]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def fmt_tokens(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1e6:.{0 if value >= 10_000_000 else 1}f}M"
    if value >= 1_000:
        return f"{value / 1e3:.{0 if value >= 10_000 else 1}f}k"
    return str(value)


@dataclass(frozen=True)
class SeriesStats:
    mean: float | None
    solved: int
    n_tasks: int
    mean_cost: float | None
    total_cost: float | None
    input_tokens: int | None
    cache_tokens: int | None
    output_tokens: int | None
    attempts: int = 0
    errors: int = 0
    completion_rate: float | None = None


def _total(values: list[int]) -> int | None:
    return sum(values) if values else None


def series_stats(tasks: list[TaskRow], key: str) -> SeriesStats:
    """One configuration's aggregate over its task cells (cell = all attempts).

    The single source of these semantics for the report, viewer, and history
    export. A task counts as solved only when every attempt in its cell has a
    reward of 1.0 — an errored attempt (no reward) fails the cell. Cost and
    token totals sum every attempt that recorded usage, errored or not: spend
    is spend.
    """
    cells = [task.by_series[key] for task in tasks if task.by_series.get(key)]
    attempts = [t for cell in cells for t in cell if not t.pending]
    cell_means = [m for task in tasks if (m := task.cell_mean(key)) is not None]
    costs = [t.cost_usd for t in attempts if t.cost_usd is not None]
    solved = sum(
        1
        for cell in cells
        if all(t.reward is not None and t.reward >= 1.0 and not t.error and not t.pending for t in cell)
    )
    return SeriesStats(
        mean=mean(cell_means),
        solved=solved,
        n_tasks=len(cells),
        attempts=len(attempts),
        errors=sum(t.error is not None or t.reward is None for t in attempts),
        completion_rate=sum(t.reward == 1.0 and not t.error for t in attempts) / len(attempts) if attempts else None,
        mean_cost=sum(costs) / len(costs) if costs else None,
        total_cost=sum(costs) if costs else None,
        input_tokens=_total(
            [t.input_tokens for t in attempts if t.input_tokens is not None]
        ),
        cache_tokens=_total(
            [t.cache_tokens for t in attempts if t.cache_tokens is not None]
        ),
        output_tokens=_total(
            [t.output_tokens for t in attempts if t.output_tokens is not None]
        ),
    )


def build_html(
    trials: list[Trial], title: str, run_names: str,
    nav_html: str = "", extra_html: str = "", refresh: int | None = None,
    *, illustrative: bool = False,
) -> str:
    from expo_harbor_evals.report_view import render_report
    return render_report(trials, title, run_names, nav_html, extra_html, refresh, illustrative=illustrative)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        type=Path,
        nargs="+",
        help="Harbor runs, native calibration, standalone candidate or downloaded EAS evidence directories",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("outputs/eval-report.html"),
        help="HTML file to write",
    )
    parser.add_argument("--title", default="Expo Harbor eval report")
    args = parser.parse_args()

    _, trials = load_runs(args.run_dirs)
    if not trials:
        raise SystemExit(f"No trial results found under {args.run_dirs}")

    run_names = ", ".join(d.name for d in args.run_dirs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(trials, args.title, run_names))
    print(f"Wrote {args.output} ({len(trials)} trials)")


if __name__ == "__main__":
    main()
