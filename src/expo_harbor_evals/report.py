"""Render a self-contained HTML report from one or more Harbor run directories.

Reads each trial's result.json plus verifier/reward-details.json and emits a
single HTML file: headline stats, mean-reward-by-configuration, a per-task
reward chart, and per-criterion judge detail. Configurations are one series
per (agent, model) pair, so baseline/oracle runs and model/effort ladders can
be merged into one report:

    uv run expo-eval-report runs/codegen-judge runs/codegen-models

Stdlib only, so it runs anywhere the repo does.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    output_tokens: int | None

    @property
    def series_key(self) -> str:
        return f"{self.agent}|{self.model}"


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
            t.reward for t in self.by_series.get(key, []) if t.reward is not None
        ]

    def cell_mean(self, key: str) -> float | None:
        return mean(self.cell_rewards(key))


def series_for(agent: str, model: str) -> Series:
    if agent == "nop":
        return Series(key=f"{agent}|{model}", label="Baseline (no-op)", rank=(0,))
    if agent == "oracle":
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


def read_json(path: Path) -> dict | list | None:
    """Read JSON, returning None for missing, torn, or mid-write files."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_runs(run_dirs: list[Path]) -> tuple[dict, list[Trial]]:
    job: dict = {}
    trials: list[Trial] = []
    for run_dir in run_dirs:
        if not job:
            job = read_json(run_dir / "result.json") or {}
        for trial_result in sorted(run_dir.glob("*/result.json")):
            raw = read_json(trial_result)
            if not isinstance(raw, dict):
                continue
            verifier_result = raw.get("verifier_result") or {}
            rewards = verifier_result.get("rewards") or {}
            exception = raw.get("exception_info") or None
            if isinstance(exception, dict):
                exception = exception.get("exception_message") or str(exception)

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
                    reward=rewards.get("reward"),
                    criteria=criteria,
                    judge=judge,
                    error=exception,
                    cost_usd=agent_result.get("cost_usd"),
                    output_tokens=agent_result.get("n_output_tokens"),
                )
            )
    return job, trials


def build_series(trials: list[Trial]) -> list[Series]:
    by_key: dict[str, Series] = {}
    for trial in trials:
        by_key.setdefault(trial.series_key, series_for(trial.agent, trial.model))
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


@dataclass(frozen=True)
class SeriesStats:
    mean: float | None
    solved: int
    n_tasks: int
    mean_cost: float | None


def series_stats(tasks: list[TaskRow], key: str) -> SeriesStats:
    """One configuration's aggregate over its task cells (cell = all attempts).

    The single source of these semantics for the report, viewer, and history
    export. A task counts as solved only when every attempt in its cell has a
    reward of 1.0 — an errored attempt (no reward) fails the cell.
    """
    cells = [task.by_series[key] for task in tasks if task.by_series.get(key)]
    cell_means = [m for task in tasks if (m := task.cell_mean(key)) is not None]
    costs = [t.cost_usd for cell in cells for t in cell if t.cost_usd is not None]
    solved = sum(
        1
        for cell in cells
        if all(t.reward is not None and t.reward >= 1.0 for t in cell)
    )
    return SeriesStats(
        mean=mean(cell_means),
        solved=solved,
        n_tasks=len(cells),
        mean_cost=sum(costs) / len(costs) if costs else None,
    )


def _bar_path(x: float, y: float, width: float, height: float, radius: float) -> str:
    """Horizontal bar: square at the baseline (left), rounded data-end (right)."""
    if width <= 0:
        return ""
    radius = min(radius, width, height / 2)
    return (
        f"M{x:.1f},{y:.1f} h{width - radius:.1f} "
        f"a{radius:.1f},{radius:.1f} 0 0 1 {radius:.1f},{radius:.1f} "
        f"v{height - 2 * radius:.1f} "
        f"a{radius:.1f},{radius:.1f} 0 0 1 -{radius:.1f},{radius:.1f} "
        f"h-{width - radius:.1f} z"
    )


def _grid(left: float, top: float, plot_w: float, bottom_y: float) -> list[str]:
    parts = []
    for i in range(5):
        gx = left + plot_w * i / 4
        parts.append(
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{bottom_y}" '
            'class="grid"/>'
        )
        parts.append(
            f'<text x="{gx:.1f}" y="{bottom_y + 16}" class="tick" '
            f'text-anchor="middle">{i / 4:.2f}</text>'
        )
    parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom_y}" class="axis"/>'
    )
    return parts


def render_summary_chart(series: list[Series], stats: dict[str, SeriesStats]) -> str:
    left, right, top, bottom = 190, 64, 10, 30
    bar_h, row_h, plot_w = 16, 34, 620
    width = left + plot_w + right
    height = top + row_h * len(series) + bottom

    parts = _grid(left, top, plot_w, height - bottom)
    for index, entry in enumerate(series):
        value = stats[entry.key].mean
        row_top = top + index * row_h
        bar_y = row_top + (row_h - bar_h) / 2
        parts.append(
            f'<text x="{left - 10}" y="{row_top + row_h / 2 + 4}" class="cat" '
            f'text-anchor="end">{html.escape(entry.label)}</text>'
        )
        bar_w = plot_w * max(0.0, min(1.0, value or 0.0))
        path = _bar_path(left + 0.5, bar_y, bar_w, bar_h, 4)
        if path:
            parts.append(f'<path d="{path}" class="bar {entry.css}"/>')
        parts.append(
            f'<text x="{left + bar_w + 8:.1f}" y="{bar_y + bar_h - 4}" '
            f'class="val">{fmt(value)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="group" '
        f'aria-label="Mean reward by configuration">{"".join(parts)}</svg>'
    )


def render_task_chart(tasks: list[TaskRow], series: list[Series]) -> str:
    left, right, top, bottom = 250, 64, 10, 30
    bar_h, bar_gap = 12, 2
    group_h = len(series) * bar_h + (len(series) - 1) * bar_gap
    row_h = group_h + 22
    plot_w = 560
    width = left + plot_w + right
    height = top + row_h * len(tasks) + bottom

    parts = _grid(left, top, plot_w, height - bottom)
    for row_index, task in enumerate(tasks):
        row_top = top + row_index * row_h
        y0 = row_top + (row_h - group_h) / 2
        label = task.name
        id_match = re.match(r"((?:expo-(?:sdk|router|ui)|simbench-ios)-\d+)-(.*)", label)
        line1, line2 = (
            (id_match.group(1), id_match.group(2)) if id_match else (label, "")
        )
        if len(line2) > 36:
            line2 = line2[:35] + "…"
        label_x = left - 10
        if line2:
            parts.append(
                f'<text x="{label_x}" y="{row_top + row_h / 2 - 2}" class="cat" '
                f'text-anchor="end"><tspan font-weight="600">{html.escape(line1)}'
                f'</tspan><tspan x="{label_x}" dy="14" class="cat2">'
                f"{html.escape(line2)}</tspan></text>"
            )
        else:
            parts.append(
                f'<text x="{label_x}" y="{row_top + row_h / 2 + 4}" class="cat" '
                f'text-anchor="end">{html.escape(line1)}</text>'
            )
        for series_index, entry in enumerate(series):
            cell_mean = task.cell_mean(entry.key)
            value = cell_mean if cell_mean is not None else 0.0
            bar_y = y0 + series_index * (bar_h + bar_gap)
            bar_w = plot_w * max(0.0, min(1.0, value))
            path = _bar_path(left + 0.5, bar_y, bar_w, bar_h, 4)
            if path:
                parts.append(f'<path d="{path}" class="bar {entry.css}"/>')
            parts.append(
                f'<text x="{left + bar_w + 8:.1f}" y="{bar_y + bar_h - 2.5}" '
                f'class="val vs">{fmt(cell_mean)}</text>'
            )
        parts.append(
            f'<rect x="0" y="{row_top}" width="{width}" height="{row_h}" '
            f'class="hit" tabindex="0" role="img" data-task="{row_index}" '
            f'aria-label="{html.escape(label)}"/>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="group" '
        f'aria-label="Reward by task and configuration">{"".join(parts)}</svg>'
    )


def render_summary_table(series: list[Series], stats: dict[str, SeriesStats]) -> str:
    rows = []
    for entry in series:
        stat = stats[entry.key]
        cost = stat.mean_cost
        rows.append(
            "<tr>"
            f'<td><span class="swatch {entry.css}"></span> '
            f"{html.escape(entry.label)}</td>"
            f'<td class="num">{fmt(stat.mean)}</td>'
            f'<td class="num">{stat.solved}/{stat.n_tasks}</td>'
            f'<td class="num">{f"${cost:.2f}" if cost is not None else "—"}</td>'
            "</tr>"
        )
    return (
        '<table><thead><tr><th>Configuration</th><th class="num">Mean reward</th>'
        '<th class="num">Solved (all attempts)</th><th class="num">Agent cost</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _criterion_chip(records: list[dict]) -> str:
    """Aggregate one criterion's verdicts across attempts into a chip."""
    passes = sum(1 for r in records if float(r.get("value") or 0.0) >= 1.0)
    total = len(records)
    if passes == total:
        chip = '<span class="chip pass">✓ pass</span>'
    elif passes == 0:
        chip = '<span class="chip fail">✕ fail</span>'
    else:
        chip = f'<span class="chip mixed">◐ {passes}/{total}</span>'

    reasons = []
    for attempt_index, record in enumerate(records):
        reasoning = (record.get("reasoning") or "").strip()
        if not reasoning:
            continue
        verdict = "pass" if float(record.get("value") or 0.0) >= 1.0 else "fail"
        prefix = f"Attempt {attempt_index + 1} — {verdict}: " if len(records) > 1 else ""
        reasons.append(
            f'<p class="reason">{html.escape(prefix)}{html.escape(reasoning)}</p>'
        )
    if not reasons:
        return chip
    return f"<details><summary>{chip}</summary>{''.join(reasons)}</details>"


def render_criteria_table(task: TaskRow, series: list[Series]) -> str:
    reference = next(
        (
            trial.criteria
            for entry in series
            for trial in task.by_series.get(entry.key, [])
            if trial.criteria
        ),
        [],
    )
    if not reference:
        return '<p class="muted">No judge detail recorded for this task.</p>'

    heads = "".join(f"<th>{html.escape(entry.label)}</th>" for entry in series)
    body: list[str] = []
    for criterion_index, criterion in enumerate(reference):
        name = criterion.get("name", f"criterion-{criterion_index}")
        description = criterion.get("description", "")
        cells = []
        for entry in series:
            records = [
                record
                for trial in task.by_series.get(entry.key, [])
                for record in trial.criteria
                if record.get("name") == name
            ]
            if not records:
                cells.append('<td><span class="muted">—</span></td>')
                continue
            cells.append(f"<td>{_criterion_chip(records)}</td>")
        body.append(
            "<tr>"
            f'<td class="crit"><strong>{html.escape(name)}</strong>'
            f'<span class="desc">{html.escape(description)}</span></td>'
            f"{''.join(cells)}</tr>"
        )
    return (
        "<table><thead><tr><th>Criterion</th>"
        f"{heads}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def build_html(
    trials: list[Trial],
    title: str,
    run_names: str,
    nav_html: str = "",
    extra_html: str = "",
    refresh: int | None = None,
) -> str:
    tasks = group_tasks(trials)
    series = build_series(trials)
    stats = {entry.key: series_stats(tasks, entry.key) for entry in series}
    refresh_meta = (
        f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    )

    errors = [t for t in trials if t.error]
    criteria_count = sum(len(t.criteria) for t in trials)
    judge = next((t.judge for t in trials if t.judge), {})
    judge_label = judge.get("agent") or (
        judge.get("model") or "programmatic (no LLM)"
    )
    if judge.get("agent") and judge.get("model"):
        judge_label = f"{judge['agent']} · {judge['model']}"
    attempts_per_cell = max(
        (len(cell) for task in tasks for cell in task.by_series.values()),
        default=1,
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tiles = (
        f'<div class="tile"><div class="label">Tasks</div>'
        f'<div class="value">{len(tasks)}</div></div>'
        f'<div class="tile"><div class="label">Configurations</div>'
        f'<div class="value">{len(series)}</div></div>'
        f'<div class="tile"><div class="label">Trials</div>'
        f'<div class="value">{len(trials)}</div>'
        f'<div class="sub">{len(errors)} errored · up to {attempts_per_cell} '
        f"attempts/cell</div></div>"
        f'<div class="tile"><div class="label">Criteria judged</div>'
        f'<div class="value">{criteria_count}</div>'
        f'<div class="sub">judge: {html.escape(str(judge_label))}</div></div>'
    )

    legend = "".join(
        f'<span class="key"><span class="swatch {entry.css}"></span>'
        f"{html.escape(entry.label)}</span>"
        for entry in series
    )

    sections = []
    for task in tasks:
        sections.append(
            f"<section><h3>{html.escape(task.name)}</h3>"
            f"{render_criteria_table(task, series)}</section>"
        )

    tooltip_data = []
    for task in tasks:
        rows = []
        for entry in series:
            attempts = task.cell_rewards(entry.key)
            value = fmt(task.cell_mean(entry.key))
            if len(attempts) > 1:
                value += " (" + ", ".join(f"{r:.2f}" for r in attempts) + ")"
            rows.append({"agent": entry.label, "css": entry.css, "value": value})
        tooltip_data.append({"task": task.name, "series": rows})

    series_css_light = "\n".join(
        f"  .{entry.css} {{ --series: {entry.light}; }}" for entry in series
    )
    series_css_dark = "\n".join(
        f"    .{entry.css} {{ --series: {entry.dark}; }}" for entry in series
    )

    error_block = ""
    if errors:
        items = "".join(
            f"<li><strong>{html.escape(t.task)}</strong> "
            f"({html.escape(t.agent)} {html.escape(t.model)}): "
            f"{html.escape(str(t.error))}</li>"
            for t in errors
        )
        error_block = (
            f'<section><h3>Errored trials</h3><ul class="errors">{items}</ul></section>'
        )

    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
{refresh_meta}<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --good: #0ca30c; --critical: #d03b3b; --warning: #fab219;
}}
{series_css_light}
@media (prefers-color-scheme: dark) {{
  :root {{
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --good: #0ca30c; --critical: #d03b3b; --warning: #fab219;
  }}
{series_css_dark}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}}
main {{ max-width: 1020px; margin: 0 auto; padding: 32px 24px 64px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 36px 0 12px; }}
h3 {{ font-size: 14px; margin: 28px 0 8px; }}
.meta {{ color: var(--text-secondary); font-size: 13px; margin-bottom: 24px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
.tile {{
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px;
}}
.tile .label {{ font-size: 12px; color: var(--text-secondary); }}
.tile .value {{ font-size: 30px; font-weight: 600; margin-top: 2px; }}
.tile .sub {{ font-size: 12px; color: var(--muted); }}
.card {{
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 18px; margin-top: 12px;
}}
.legend {{ display: flex; flex-wrap: wrap; gap: 12px 18px; font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }}
.key {{ display: inline-flex; align-items: center; gap: 6px; }}
.swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; background: var(--series); vertical-align: -1px; }}
svg {{ width: 100%; height: auto; display: block; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.axis {{ stroke: var(--axis); stroke-width: 1; }}
.tick, .val {{ font: 11px system-ui, sans-serif; fill: var(--muted); }}
.val {{ font-variant-numeric: tabular-nums; fill: var(--text-secondary); }}
.val.vs {{ font-size: 10px; }}
.cat {{ font: 12px system-ui, sans-serif; fill: var(--text-secondary); }}
.cat2 {{ fill: var(--muted); font-size: 11px; }}
.bar {{ fill: var(--series); }}
.hit {{ fill: transparent; outline: none; }}
.hit:focus-visible {{ stroke: var(--text-primary); stroke-width: 1.5; fill: rgba(128,128,128,0.06); }}
.hit:hover {{ fill: rgba(128,128,128,0.06); }}
#tooltip {{
  position: fixed; pointer-events: none; z-index: 10; display: none;
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  max-width: 340px;
}}
#tooltip .t-task {{ color: var(--text-secondary); margin-bottom: 4px; }}
#tooltip .t-row {{ display: flex; align-items: center; gap: 6px; }}
#tooltip .t-key {{ width: 10px; height: 3px; border-radius: 2px; background: var(--series); }}
#tooltip .t-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
#tooltip .t-agent {{ color: var(--text-secondary); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
th, td {{ text-align: left; padding: 8px 10px; border-top: 1px solid var(--grid); vertical-align: top; }}
thead th {{ border-top: 0; font-size: 11.5px; color: var(--text-secondary); font-weight: 500; background: color-mix(in srgb, var(--surface-1) 92%, var(--text-primary)); }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.crit .desc {{ display: block; color: var(--text-secondary); }}
.chip {{ display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; border: 1px solid; white-space: nowrap; }}
.chip.pass {{ color: var(--good); border-color: var(--good); }}
.chip.fail {{ color: var(--critical); border-color: var(--critical); }}
.chip.mixed {{ color: var(--text-secondary); border-color: var(--warning); }}
details summary {{ cursor: pointer; list-style: none; }}
details summary::-webkit-details-marker {{ display: none; }}
details .reason {{ margin: 6px 0 0; color: var(--text-secondary); font-size: 12px; }}
.errors li {{ color: var(--text-secondary); }}
.muted {{ color: var(--muted); }}
footer {{ margin-top: 40px; font-size: 12px; color: var(--muted); }}
</style>
<main>{nav_html}
  <h1>{html.escape(title)}</h1>
  <div class="meta">
    Runs: <strong>{html.escape(run_names)}</strong>
    · judge: {html.escape(str(judge_label))}
    · report generated {generated}
  </div>
  <div class="tiles">{tiles}</div>
  <h2>Mean reward by configuration</h2>
  <div class="card">
    {render_summary_chart(series, stats)}
    {render_summary_table(series, stats)}
  </div>
  <h2>Reward by task</h2>
  <div class="card">
    <div class="legend">{legend}</div>
    {render_task_chart(tasks, series)}
  </div>
  <h2>Per-criterion judge detail</h2>
  {"".join(sections)}
  {error_block}
  {extra_html}
  <footer>
    expo-codegen tasks imported from callstackincubator/evals (MIT) · scored with
    harbor-rewardkit · run with Harbor. Rewards are weighted means of binary
    criteria in [0, 1]; agent cost is the mean claude CLI cost per task.
  </footer>
</main>
<div id="tooltip" role="status"></div>
<script type="application/json" id="chart-data">{json.dumps(tooltip_data)}</script>
<script>
(function () {{
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  const tooltip = document.getElementById("tooltip");

  function fill(index) {{
    const record = data[index];
    if (!record) return false;
    tooltip.replaceChildren();
    const taskLine = document.createElement("div");
    taskLine.className = "t-task";
    taskLine.textContent = record.task;
    tooltip.appendChild(taskLine);
    for (const series of record.series) {{
      const row = document.createElement("div");
      row.className = "t-row";
      const key = document.createElement("span");
      key.className = "t-key " + series.css;
      const value = document.createElement("span");
      value.className = "t-val";
      value.textContent = series.value;
      const agent = document.createElement("span");
      agent.className = "t-agent";
      agent.textContent = series.agent;
      row.append(key, value, agent);
      tooltip.appendChild(row);
    }}
    return true;
  }}

  function place(x, y) {{
    const pad = 14;
    tooltip.style.display = "block";
    const rect = tooltip.getBoundingClientRect();
    let left = x + pad, top = y + pad;
    if (left + rect.width > window.innerWidth - 8) left = x - rect.width - pad;
    if (top + rect.height > window.innerHeight - 8) top = y - rect.height - pad;
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }}

  document.querySelectorAll(".hit").forEach((hit) => {{
    const index = Number(hit.dataset.task);
    hit.addEventListener("pointermove", (event) => {{
      if (fill(index)) place(event.clientX, event.clientY);
    }});
    hit.addEventListener("pointerleave", () => (tooltip.style.display = "none"));
    hit.addEventListener("focus", () => {{
      if (!fill(index)) return;
      const box = hit.getBoundingClientRect();
      place(box.left + 260, box.top + box.height / 2);
    }});
    hit.addEventListener("blur", () => (tooltip.style.display = "none"));
  }});
}})();
</script>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        type=Path,
        nargs="+",
        help="Harbor run directories (runs/<job>), merged into one report",
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
