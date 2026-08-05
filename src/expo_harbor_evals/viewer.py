"""Local web viewer for Harbor runs: browse every eval, watch live progress.

Serves a small site over the runs directory. Pages are rebuilt from disk on
every request, so an in-flight `harbor run` shows up as it writes trials;
active pages auto-refresh. Stdlib only, binds to localhost.

    uv run expo-eval-viewer            # serves runs/ on http://127.0.0.1:4477
"""

from __future__ import annotations

import argparse
import html
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from expo_harbor_evals.report import (
    build_html,
    build_series,
    fmt,
    group_tasks,
    load_runs,
    read_json,
    series_stats,
)

ACTIVE_WINDOW_SEC = 120

BASE_CSS = """
:root {
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
  --good: #0ca30c; --critical: #d03b3b; --warning: #b96f00; --accent: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
    --warning: #fab219; --accent: #3987e5;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1020px; margin: 0 auto; padding: 28px 24px 64px; }
h1 { font-size: 20px; margin: 0 0 16px; }
h2 { font-size: 15px; margin: 28px 0 10px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.nav { font-size: 13px; color: var(--text-secondary); margin-bottom: 18px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 9px 12px; border-top: 1px solid var(--grid); vertical-align: top; }
thead th { border-top: 0; font-size: 12px; color: var(--text-secondary);
  font-weight: 500; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
  font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid; }
.chip.running { color: var(--accent); border-color: var(--accent); }
.chip.finished { color: var(--text-secondary); border-color: var(--grid); }
.chip.stopped { color: var(--warning); border-color: var(--warning); }
.chip.pass { color: var(--good); border-color: var(--good); }
.chip.fail { color: var(--critical); border-color: var(--critical); }
.muted { color: var(--muted); }
.series { color: var(--text-secondary); font-size: 12.5px; }
pre { background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px; overflow-x: auto; font-size: 12px;
  white-space: pre-wrap; word-break: break-word; }
.kv td:first-child { color: var(--text-secondary); width: 200px; }
"""


@dataclass
class RunSummary:
    name: str
    path: Path
    status: str
    n_trials: int
    updated: float
    headline: str


def page(title: str, body: str, refresh: int | None = None) -> str:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{meta}<title>{html.escape(title)}</title>"
        f"<style>{BASE_CSS}</style><main>{body}</main></html>"
    )


def humanize(ts: float) -> str:
    delta = time.time() - ts
    if delta < 90:
        return f"{int(delta)}s ago"
    if delta < 5400:
        return f"{int(delta / 60)}m ago"
    if delta < 129600:
        return f"{int(delta / 3600)}h ago"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def latest_mtime(run_dir: Path) -> float:
    newest = run_dir.stat().st_mtime
    for candidate in run_dir.glob("*/result.json"):
        newest = max(newest, candidate.stat().st_mtime)
    return newest


def run_status(job: dict, updated: float) -> str:
    if job.get("finished_at"):
        return "finished"
    return "running" if time.time() - updated < ACTIVE_WINDOW_SEC else "stopped"


def summarize_run(run_dir: Path) -> RunSummary:
    job, trials = load_runs([run_dir])
    updated = latest_mtime(run_dir)
    series = build_series(trials)
    tasks = group_tasks(trials)
    parts = [
        f"{entry.label} {fmt(series_stats(tasks, entry.key).mean)}"
        for entry in series
    ]
    headline = " · ".join(parts[:5]) + (" · …" if len(parts) > 5 else "")
    return RunSummary(
        name=run_dir.name,
        path=run_dir,
        status=run_status(job, updated),
        n_trials=len(trials),
        updated=updated,
        headline=headline or "no trials yet",
    )


def render_index(runs_dir: Path) -> str:
    run_dirs = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir()),
        key=latest_mtime,
        reverse=True,
    )
    rows = []
    any_running = False
    for run_dir in run_dirs:
        try:
            summary = summarize_run(run_dir)
        except Exception as error:  # a malformed run must not break the index
            rows.append(
                f"<tr><td>{html.escape(run_dir.name)}</td><td colspan=4>"
                f'<span class="muted">unreadable: {html.escape(str(error))}</span>'
                "</td></tr>"
            )
            continue
        any_running = any_running or summary.status == "running"
        rows.append(
            "<tr>"
            f'<td><a href="/run/{summary.name}">{html.escape(summary.name)}</a></td>'
            f'<td><span class="chip {summary.status}">{summary.status}</span></td>'
            f'<td class="num">{summary.n_trials}</td>'
            f'<td class="series">{html.escape(summary.headline)}</td>'
            f'<td class="muted">{humanize(summary.updated)}</td>'
            "</tr>"
        )
    body = (
        "<h1>Expo Harbor evals</h1>"
        f'<div class="nav">{len(run_dirs)} runs in {html.escape(str(runs_dir))}'
        " · refreshes automatically</div>"
        "<table><thead><tr><th>Run</th><th>Status</th>"
        '<th class="num">Trials</th><th>Mean reward by configuration</th>'
        "<th>Updated</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"{render_history_section()}"
    )
    return page("Expo Harbor evals", body, refresh=10)


def render_history_section(history_path: Path = Path("results/history.jsonl")) -> str:
    """Results-over-time from the exported history file (empty when absent)."""
    if not history_path.exists():
        return (
            '<h2>History</h2><p class="muted">No exported history yet — run '
            "<code>make export</code> after a finished run to start the time "
            "series.</p>"
        )
    entries = []
    for line in history_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    if not entries:
        return ""
    entries.sort(key=lambda e: e.get("finished_at") or "")
    rows = []
    for entry in entries:
        headline = " · ".join(
            f"{s['label']} {s['mean']:.2f}"
            for s in entry.get("series", [])
            if s.get("mean") is not None
        )
        finished = str(entry.get("finished_at", ""))[:16].replace("T", " ")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(entry.get('run', '')))}</td>"
            f'<td class="muted">{html.escape(finished)}</td>'
            f'<td class="num">{entry.get("n_trials", "")}</td>'
            f'<td class="series">{html.escape(headline)}</td>'
            "</tr>"
        )
    return (
        "<h2>History</h2>"
        '<div class="nav">Exported snapshots from results/history.jsonl — '
        "re-export after each run to track results over time.</div>"
        "<table><thead><tr><th>Run</th><th>Finished</th>"
        '<th class="num">Trials</th><th>Mean reward by configuration</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_run(runs_dir: Path, name: str) -> str | None:
    run_dir = runs_dir / name
    if not run_dir.is_dir():
        return None
    job, trials = load_runs([run_dir])
    status = run_status(job, latest_mtime(run_dir))
    if not trials:
        return page(
            name,
            f'<div class="nav"><a href="/">← all runs</a></div>'
            f"<h1>{html.escape(name)}</h1><p class='muted'>No trials yet.</p>",
            refresh=10 if status == "running" else None,
        )

    trial_rows = []
    for trial in sorted(trials, key=lambda t: t.name):
        state = (
            '<span class="chip fail">error</span>'
            if trial.error
            else f'<span class="num">{fmt(trial.reward)}</span>'
        )
        trial_rows.append(
            "<tr>"
            f'<td><a href="/run/{name}/trial/{trial.name}">'
            f"{html.escape(trial.name)}</a></td>"
            f"<td>{html.escape(trial.task)}</td>"
            f"<td>{html.escape(trial.agent + (' · ' + trial.model if trial.model else ''))}</td>"
            f'<td class="num">{state}</td>'
            "</tr>"
        )
    trials_table = (
        "<h2>Trials</h2><table><thead><tr><th>Trial</th><th>Task</th>"
        '<th>Agent</th><th class="num">Reward</th></tr></thead>'
        f"<tbody>{''.join(trial_rows)}</tbody></table>"
    )
    nav = (
        f'<div class="nav" style="font: 13px system-ui, sans-serif; margin-bottom: 14px;">'
        f'<a href="/" style="color: inherit;">← all runs</a></div>'
    )
    return build_html(
        trials,
        f"{name} — {status}",
        name,
        nav_html=nav,
        extra_html=trials_table,
        refresh=30 if status == "running" else None,
    )


def render_trial(runs_dir: Path, run_name: str, trial_name: str) -> str | None:
    trial_dir = runs_dir / run_name / trial_name
    raw = read_json(trial_dir / "result.json")
    if raw is None:
        return None

    agent = raw.get("agent_info") or {}
    model = (agent.get("model_info") or {}).get("name") or ""
    rewards = (raw.get("verifier_result") or {}).get("rewards") or {}
    agent_result = raw.get("agent_result") or {}
    metadata = agent_result.get("metadata") or {}
    exception = raw.get("exception_info")

    sections: list[str] = []
    info_rows = {
        "Task": raw.get("task_name", ""),
        "Agent": f"{agent.get('name') or ''}"
        + (f" · {model}" if model else ""),
        "Started": str(raw.get("started_at") or "")[:19].replace("T", " "),
        "Finished": str(raw.get("finished_at") or "")[:19].replace("T", " "),
        "Agent cost": f"${agent_result['cost_usd']:.2f}"
        if agent_result.get("cost_usd") is not None
        else "—",
        "Agent turns": str(metadata.get("num_turns") or "—"),
    }
    sections.append(
        '<table class="kv"><tbody>'
        + "".join(
            f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
            for k, v in info_rows.items()
        )
        + "</tbody></table>"
    )

    if exception:
        message = exception if isinstance(exception, str) else json.dumps(
            exception, indent=2
        )
        sections.append(
            f"<h2>Exception</h2><pre>{html.escape(str(message)[:4000])}</pre>"
        )

    if rewards:
        sections.append(
            "<h2>Rewards</h2><table><tbody>"
            + "".join(
                f'<tr><td>{html.escape(key)}</td><td class="num">{value}</td></tr>'
                for key, value in rewards.items()
            )
            + "</tbody></table>"
        )

    judge_details = read_json(trial_dir / "verifier" / "reward-details.json")
    if isinstance(judge_details, dict):
        reward_block = judge_details.get("reward")
        if isinstance(reward_block, dict) and reward_block.get("criteria"):
            rows = []
            for criterion in reward_block["criteria"]:
                passed = float(criterion.get("value") or 0) >= 1.0
                chip = (
                    '<span class="chip pass">✓ pass</span>'
                    if passed
                    else '<span class="chip fail">✕ fail</span>'
                )
                rows.append(
                    f"<tr><td><strong>{html.escape(str(criterion.get('name')))}"
                    f"</strong><br><span class='muted'>"
                    f"{html.escape(str(criterion.get('description') or ''))}</span></td>"
                    f"<td>{chip}<br><span class='muted'>"
                    f"{html.escape(str(criterion.get('reasoning') or ''))}</span></td></tr>"
                )
            sections.append(
                "<h2>Judge criteria</h2><table><tbody>"
                + "".join(rows)
                + "</tbody></table>"
            )

    sim_details = read_json(trial_dir / "verifier" / "details.json")
    if isinstance(sim_details, dict) and sim_details.get("checks"):
        rows = []
        for check in sim_details["checks"]:
            chip = (
                '<span class="chip pass">✓ pass</span>'
                if check.get("passed")
                else '<span class="chip fail">✕ fail</span>'
            )
            notes = check.get("notes")
            rows.append(
                f"<tr><td>{html.escape(str(check.get('name')))}"
                + (
                    f"<br><span class='muted'>{html.escape(str(notes))}</span>"
                    if notes
                    else ""
                )
                + f"</td><td>{chip}</td></tr>"
            )
        sections.append(
            "<h2>Checks</h2><table><tbody>" + "".join(rows) + "</tbody></table>"
        )
        evidence = sim_details.get("evidence")
        if evidence:
            sections.append(
                "<h2>Evidence</h2><pre>"
                + html.escape(json.dumps(evidence, indent=2)[:6000])
                + "</pre>"
            )
    elif sim_details is not None:
        sections.append(
            "<h2>Verifier details</h2><pre>"
            + html.escape(json.dumps(sim_details, indent=2)[:6000])
            + "</pre>"
        )

    agent_envelope = read_json(trial_dir / "agent" / "claude-host.json")
    if isinstance(agent_envelope, dict) and agent_envelope.get("result"):
        sections.append(
            "<h2>Agent final message</h2><pre>"
            + html.escape(str(agent_envelope["result"])[:8000])
            + "</pre>"
        )

    stdout_path = trial_dir / "verifier" / "test-stdout.txt"
    if stdout_path.exists():
        sections.append(
            "<h2>Verifier stdout</h2><pre>"
            + html.escape(stdout_path.read_text()[-3000:])
            + "</pre>"
        )

    body = (
        f'<div class="nav"><a href="/">← all runs</a> · '
        f'<a href="/run/{html.escape(run_name)}">{html.escape(run_name)}</a></div>'
        f"<h1>{html.escape(trial_name)}</h1>" + "".join(sections)
    )
    return page(trial_name, body)


class ViewerHandler(BaseHTTPRequestHandler):
    runs_dir: Path = Path("runs")

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parts = [unquote(p) for p in self.path.strip("/").split("/") if p]
        # Path segments become directory names; reject traversal outright.
        if any(part in ("..", ".") or "/" in part for part in parts):
            self.send_error(400)
            return
        try:
            if not parts:
                document = render_index(self.runs_dir)
            elif parts[0] == "run" and len(parts) == 2:
                document = render_run(self.runs_dir, parts[1])
            elif parts[0] == "run" and len(parts) == 4 and parts[2] == "trial":
                document = render_trial(self.runs_dir, parts[1], parts[3])
            else:
                document = None
        except Exception as error:  # render errors as a page, keep serving
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                page("error", f"<pre>{html.escape(str(error))}</pre>").encode()
            )
            return
        if document is None:
            self.send_error(404)
            return
        payload = document.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs_dir", type=Path, nargs="?", default=Path("runs"))
    parser.add_argument("--port", type=int, default=4477)
    args = parser.parse_args()

    if not args.runs_dir.is_dir():
        raise SystemExit(f"runs directory not found: {args.runs_dir}")

    ViewerHandler.runs_dir = args.runs_dir.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ViewerHandler)
    print(f"Serving {ViewerHandler.runs_dir} on http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
