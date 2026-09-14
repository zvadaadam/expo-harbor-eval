"""Portable, offline presentation of recorded evaluation outcomes."""

from __future__ import annotations

import base64
import hashlib
import html
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from expo_harbor_evals.catalog import theme_css
from expo_harbor_evals.report import Trial, _series_for, build_series, fmt, fmt_tokens, group_tasks, series_stats

LANES = {
    "native-ui": ("Native app behavior", "Built candidate apps · native UI checks", "Experimental. Calibrate the reference and broken apps on the target runtime before interpreting model results."),
    "source-review": ("Source review", "Submitted code · criterion-based judging", "A source score measures the declared code criteria. It does not establish that the app builds or works on a device."),
    "device-use": ("Simulator operation", "Fixed apps · model and driver behavior", "These trials measure operating a known app. They do not measure the quality of generated Expo code."),
    "reference-smoke": ("Reference smoke checks", "Exact reference matching · harness plumbing", "Passing verifies the smoke-check contract, not general coding ability."),
    "unversioned": ("Unversioned results", "Historical or missing experiment identity", "Experiment provenance is incomplete. Keep these records separate from versioned comparisons."),
}
LABELS = {"pass": "Pass", "partial": "Partial", "fail": "Fail", "error": "Execution error", "pending": "Pending"}
SYMBOLS = {"pass": "✓", "partial": "◐", "fail": "×", "error": "!", "pending": "·"}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def lane_for(trial: Trial) -> str:
    return trial.measurement if trial.measurement in LANES else "unversioned"


def coverage(trials: list[Trial]) -> tuple[set[str], int | None]:
    """Only explicit plans supply denominators; never assume absent trials pass."""
    tasks = {t.task for t in trials}
    runs = {}
    for t in trials:
        tasks.update(t.planned_tasks)
        runs[t.run] = (t.planned_tasks, t.planned_attempts)
    expected = sum(len(names) * count for names, count in runs.values()) if runs and all(
        names and count for names, count in runs.values()) else None
    return tasks, expected


def trial_id(trial: Trial) -> str:
    key = f"{trial.source_dir}|{trial.run}|{trial.task}|{trial.name}|{trial.series_key}"
    return "trial-" + hashlib.sha256(key.encode()).hexdigest()[:16]


def short_task(name: str) -> str:
    return name.replace("simbench-ios-", "").replace("goldenlab-", "").replace("goldennotes-", "").replace("-", " ")


def dots(trials: list[Trial]) -> str:
    return "".join(f'<a class="attempt {t.outcome}" href="#{trial_id(t)}" '
                   f'aria-label="{esc(t.name)}: {LABELS[t.outcome]}" title="{esc(t.name)}: {LABELS[t.outcome]}">'
                   f'{SYMBOLS[t.outcome]}</a>' for t in trials)


def stack(trials: list[Trial], expected: int | None) -> str:
    counts = Counter(t.outcome for t in trials)
    missing = max(0, (expected or 0) - len(trials))
    total = max(len(trials) + missing, 1)
    parts = [f'<span class="segment {state}" style="width:{count / total * 100:.3f}%" '
             f'title="{count} {LABELS[state].lower()}"></span>' for state, count in counts.items()]
    if missing:
        parts.append(f'<span class="segment missing" style="width:{missing / total * 100:.3f}%" title="{missing} missing results"></span>')
    label = ", ".join(f"{n} {LABELS[s].lower()}" for s, n in counts.items())
    return f'<div class="outcome-bar" role="img" aria-label="{esc(label)}; {missing} missing">{"".join(parts)}</div>'


def render_configurations(trials: list[Trial]) -> str:
    rows = []
    tasks = group_tasks(trials)
    for entry in build_series(trials):
        records = [t for t in trials if t.series_key == entry.key]
        first = records[0]
        names, expected = coverage(records)
        stat = series_stats(tasks, entry.key)
        counts = Counter(t.outcome for t in records)
        missing = max(0, (expected or 0) - len(records))
        plan = f"{stat.attempts}/{expected} outcomes" if expected is not None else f"{stat.attempts} outcomes · plan unknown"
        details = [first.backend or "backend not recorded", f"experiment {first.experiment[:8]}" if first.experiment else "unversioned"]
        cost_known = sum(t.cost_usd is not None for t in records)
        cost = f"${stat.total_cost:.2f}" if stat.total_cost is not None else "Not recorded"
        rows.append(f'''<tr>
          <td class="configuration"><strong>{esc(_series_for(first.agent, first.model).label)}</strong>
            <small>{esc(' · '.join(details))}</small>{stack(records, expected)}
            <small>{counts['pass']} pass · {counts['partial'] + counts['fail']} incomplete · {counts['error']} errors
            · {counts['pending']} pending · {missing} missing</small></td>
          <td class="number"><strong>{counts['pass']} / {stat.attempts}</strong><small>complete attempts</small></td>
          <td class="number"><strong>{fmt(stat.mean)}</strong><small>valid scores only</small></td>
          <td class="number"><strong>{len({t.task for t in records})} / {len(names)}</strong><small>tasks observed</small><small>{plan}</small></td>
          <td class="number"><strong>{cost}</strong><small>{cost_known}/{len(records)} costs recorded</small></td>
        </tr>''')
    return '<div class="table-scroll"><table class="config-table"><thead><tr><th>Configuration</th><th>Completion</th><th>Mean score</th><th>Coverage</th><th>Agent spend</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def render_matrix(trials: list[Trial]) -> str:
    series = build_series(trials)
    names, _ = coverage(trials)
    heads = []
    for entry in series:
        first = next(t for t in trials if t.series_key == entry.key)
        heads.append(f'<th><strong>{esc(_series_for(first.agent, first.model).label)}</strong><small>{esc(first.backend or "Unspecified backend")} · {esc(first.experiment[:8] or "unversioned")}</small></th>')
    rows = []
    for name in sorted(names):
        cells = []
        for entry in series:
            condition = [t for t in trials if t.series_key == entry.key]
            records = [t for t in condition if t.task == name]
            plans = {t.run: (t.planned_tasks, t.planned_attempts) for t in condition}
            expected = sum(count for names_, count in plans.values() if name in names_) if all(
                names_ and count for names_, count in plans.values()) else None
            if not records:
                missing_label = "Not in this cohort" if expected == 0 else f"{expected} missing results" if expected else "No result recorded"
                cells.append(f'<td class="no-result">—<small>{missing_label}</small></td>')
                continue
            counts = Counter(t.outcome for t in records)
            n = len(records) - counts['pending']
            tone = "error" if counts['error'] else "pass" if counts['pass'] == len(records) else "fail" if counts['fail'] == len(records) else "partial" if n else "pending"
            missing = max(0, (expected or 0) - len(records))
            if missing and tone == "pass":
                tone = "pending"
            scores = [t.reward for t in records if t.outcome not in ("pending", "error")]
            score = fmt(sum(scores) / len(scores)) if scores else "—"
            missing_label = f'<small>{missing} missing result{"s" if missing != 1 else ""}</small>' if missing else ''
            cells.append(f'<td><div class="result-cell {tone}"><div class="cell-head"><strong>{counts["pass"]}/{n} pass</strong><span>score {score}</span></div>{dots(records)}{missing_label}</div></td>')
        rows.append(f'<tr data-task-row data-search="{esc(name.replace("-", " "))}"><th scope="row" class="task-name">{esc(short_task(name))}<small>{esc(name)}</small></th>{"".join(cells)}</tr>')
    return f'<div class="table-scroll"><table class="matrix"><thead><tr><th>Task / configuration</th>{"".join(heads)}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def evidence_files(trial: Trial) -> tuple[list[Path], str]:
    root = trial.source_dir
    if not root or not root.is_dir():
        return [], ""
    # Fixed verifier locations only. Never follow symlinks or scan an app's
    # installed dependencies/agent home in search of screenshots.
    roots = [root, root / "verifier/mobile-eval", root / "artifacts", root / "verifier"]
    images = []
    logs = []
    for folder in roots:
        images += sorted(folder.glob("*.png")) + sorted((folder / "screens").glob("*.png"))
        logs += sorted((folder / "logs").glob("*.log"))
    allowed = lambda p: p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
    images = sorted({p for p in images if allowed(p) and p.stat().st_size <= 2 * 1024 * 1024},
                    key=lambda p: ("failure" not in p.name, p.name))[:3]
    logs = [p for p in logs if allowed(p)]
    log = ""
    if trial.outcome in ("error", "fail"):
        # Cleanup logs often follow the failed build. Prefer the diagnostic
        # path recorded by a check, otherwise the latest substantive command.
        notes = " ".join(str(c.get("notes", "")) for c in trial.checks)
        selected = next((p for p in logs if p.name in notes), None)
        selected = selected or next((p for p in reversed(logs) if p.stat().st_size), None)
        if selected:
            with selected.open("rb") as stream:
                stream.seek(max(0, selected.stat().st_size - 8000))
                log = f"{selected.name}\n" + stream.read(8000).decode(errors="replace")
    return images, log


def render_trial(trial: Trial) -> str:
    outcome = trial.outcome
    records = trial.checks or trial.criteria
    steps = []
    for index, record in enumerate(records):
        passed = record.get("passed") is True if trial.checks else record.get("value") == 1
        state = "pass" if passed else "fail"
        name = record.get("name") or record.get("id") or f"Check {index + 1}"
        note = record.get("notes") or record.get("reasoning") or record.get("description") or ""
        steps.append(f'<li><span class="check-symbol {state}">{SYMBOLS[state]}</span><div><strong>{esc(name)}</strong><p>{esc(note)}</p></div></li>')
    images, log = evidence_files(trial)
    figures = []
    for path in images:
        encoded = base64.b64encode(path.read_bytes()).decode()
        figures.append(f'<figure><img loading="lazy" src="data:image/png;base64,{encoded}" alt="Recorded screenshot: {esc(path.stem)}"><figcaption>{esc(path.name)}</figcaption></figure>')
    evidence = f'<div class="screenshots">{"".join(figures)}</div>' if figures else '<p class="subtle">No screenshot embedded in this record.</p>'
    provenance = {
        "Task": trial.task, "Run": trial.run or "Not recorded", "Measurement": LANES[lane_for(trial)][0],
        "Backend": trial.backend or "Not recorded", "Experiment": trial.experiment or "Not recorded",
        "Suite": trial.provenance.get("suite") or "Not recorded",
        "Task hash": trial.provenance.get("task_sha256") or "Not recorded",
        "Source judge": " · ".join(str(trial.judge[k]) for k in ("agent", "model") if trial.judge.get(k)) or "Not recorded / programmatic",
        "Agent cost": f"${trial.cost_usd:.2f}" if trial.cost_usd is not None else "Not recorded",
        "Input / cache / output tokens": " / ".join(fmt_tokens(n) for n in (trial.input_tokens, trial.cache_tokens, trial.output_tokens)),
        "Calibration": "Not established by this report",
    }
    metadata = "".join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in provenance.items())
    score = "Pending" if trial.pending else f"Score {fmt(trial.reward)}"
    error = f'<p class="error-message">{esc(trial.error)}</p>' if trial.error else ""
    transcript = f'<details class="log"><summary>Verifier log excerpt</summary><pre>{esc(log)}</pre></details>' if log else ""
    return f'''<details class="trial-detail" id="{trial_id(trial)}" data-detail data-search="{esc(trial.task.replace('-', ' '))}">
      <summary><span class="status {outcome}">{SYMBOLS[outcome]} {LABELS[outcome]}</span>
        <span class="trial-title"><strong>{esc(short_task(trial.task))}</strong><small>{esc(_series_for(trial.agent, trial.model).label)} · {esc(trial.name)}</small></span>
        <span class="trial-score">{score}</span><span class="expand" aria-hidden="true">+</span></summary>
      <div class="trial-body">{error}<div class="evidence-columns"><div><h4>{'Native / state checks' if trial.checks else 'Source criteria'}</h4>
      <ol class="checks">{''.join(steps)}</ol>{'<p class="subtle">No check details recorded.</p>' if not steps else ''}</div><div><h4>Recorded evidence</h4>{evidence}</div></div>
      {transcript}<details class="provenance"><summary>Reproduction details</summary><dl>{metadata}</dl></details></div>
    </details>'''


CSS = theme_css() + """
:root{color-scheme:light dark;--page:var(--expo-theme-background-screen);--surface:var(--expo-theme-background-default);--ink:var(--expo-theme-text-default);--muted:var(--expo-theme-text-secondary);--line:var(--expo-theme-border-secondary);--accent:var(--expo-theme-text-link);--pass:var(--expo-theme-text-success);--pass-bg:var(--expo-theme-background-success);--partial:var(--expo-theme-text-warning);--partial-bg:var(--expo-theme-background-warning);--fail:var(--expo-theme-text-danger);--fail-bg:var(--expo-theme-background-danger);--error:var(--expo-theme-text-info);--error-bg:var(--expo-theme-background-info);--pending:var(--expo-theme-text-secondary);--pending-bg:var(--expo-theme-background-element);}

*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1280px;margin:auto;padding:32px 40px 64px}
a{color:var(--accent)}
button,input{font:inherit}
button,a,input,summary{-webkit-tap-highlight-color:transparent}
button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
button{cursor:pointer}
h1{font-size:36px;letter-spacing:-1.2px;line-height:1.16;margin:24px 0 12px;font-weight:650}
h2{font-size:21px;letter-spacing:-.45px;margin:0}
h3{font-size:16px;margin:0}
h4{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 16px}
p{margin:8px 0}
small{display:block;color:var(--muted);font-size:12px;font-weight:400;line-height:1.55}
.subtle{color:var(--muted);font-size:13px}
.topline{display:flex;align-items:center;justify-content:space-between;gap:20px;color:var(--muted);font-size:12px}
.brand{display:flex;gap:10px;align-items:center;font-size:11px;letter-spacing:.14em;font-weight:700;color:var(--ink)}
.brand-mark{width:22px;height:22px;border-radius:6px;background:var(--accent);display:grid;place-items:center;color:var(--surface);font-size:15px}
.intro{max-width:670px;color:var(--muted);font-size:16px;margin-bottom:24px}
.demo{background:var(--partial-bg);color:var(--partial);padding:12px 16px;border-radius:10px;margin:18px 0;font-weight:600}
.lane-nav{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 24px}
.lane-tab{min-height:44px;padding:10px 16px;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:9px;transition:background-color .15s,color .15s,transform .15s}
.lane-tab[aria-pressed=true]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
button:active{transform:scale(.96)}
.lane-tab span{margin-left:9px;font-size:11px;opacity:.7}
.lane-header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.eyebrow{font-size:10px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin-bottom:7px}
.lane-note{display:block;color:var(--muted);font-size:12px;background:var(--surface);border:1px solid var(--line);padding:8px 12px;border-radius:8px;max-width:440px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 26px}
.metric{padding:18px 20px;background:var(--surface);border-radius:12px;box-shadow:0 1px 2px #00000006,0 0 0 1px var(--line)}
.metric-label{font-size:12px;color:var(--muted)}
.metric-value{font-size:30px;line-height:1.3;font-variant-numeric:tabular-nums;letter-spacing:-1px;margin:7px 0}
.metric-value span{font-size:17px;color:var(--muted);letter-spacing:0}
.section-heading{display:flex;justify-content:space-between;align-items:end;gap:20px;margin:32px 0 12px}
.table-scroll{overflow:auto;background:var(--surface);border-radius:12px;box-shadow:0 1px 2px #00000006,0 0 0 1px var(--line)}
table{width:100%;border-collapse:collapse;text-align:left}
th,td{padding:16px;vertical-align:top;border-bottom:1px solid var(--line)}
thead th{background:color-mix(in srgb,var(--surface) 75%,var(--page));font-size:11px;font-weight:500;color:var(--muted)}
tbody tr:last-child>*{border-bottom:0}
thead strong{color:var(--ink);font-size:13px}
.config-table td.number{white-space:nowrap;font-variant-numeric:tabular-nums}
.number strong{font-weight:550;font-size:17px}
.configuration{min-width:290px;max-width:400px}
.configuration>strong{font-size:14px;font-weight:650}
.outcome-bar{display:flex;width:100%;height:7px;gap:2px;margin:12px 0 7px;overflow:hidden;border-radius:3px;background:var(--pending-bg)}
.segment{min-width:2px}
.segment.pass{background:var(--pass)}
.segment.partial{background:var(--partial)}
.segment.fail{background:var(--fail)}
.segment.error{background:var(--error)}
.segment.pending{background:var(--pending)}
.segment.missing{background:repeating-linear-gradient(45deg,var(--line),var(--line) 3px,var(--surface) 3px,var(--surface) 6px)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0;font-size:12px;color:var(--muted)}
.legend span{display:flex;align-items:center;gap:5px}
.status,.attempt,.check-symbol{font-size:12px;font-weight:600;border-radius:6px;display:inline-flex;align-items:center;justify-content:center}
.status{padding:5px 8px;white-space:nowrap}
.pass{color:var(--pass);background:var(--pass-bg)}
.partial{color:var(--partial);background:var(--partial-bg)}
.fail{color:var(--fail);background:var(--fail-bg)}
.error{color:var(--error);background:var(--error-bg)}
.pending{color:var(--pending);background:var(--pending-bg)}
.matrix th.task-name{min-width:235px;max-width:320px;font-size:13px;font-weight:550;text-transform:capitalize;position:sticky;left:0;background:var(--surface);z-index:1}
.task-name small{text-transform:none;font-size:10px;overflow-wrap:anywhere;opacity:.8;margin-top:3px}
.matrix td{padding:9px;min-width:180px}
.matrix thead th{min-width:180px}
.result-cell{border-radius:8px;padding:9px 10px}
.cell-head{display:flex;gap:20px;justify-content:space-between;font-size:12px;white-space:nowrap}
.cell-head span{font-size:11px;opacity:.8}
.attempt{width:40px;height:40px;text-decoration:none;font-size:17px;margin:5px 2px 0 0;border:1px solid color-mix(in srgb,currentColor 25%,transparent);transition:transform .15s}
.attempt:hover{outline:1px solid currentColor;transform:translateY(-1px)}
.no-result{text-align:center;color:var(--muted);background:repeating-linear-gradient(135deg,transparent,transparent 6px,color-mix(in srgb,var(--line) 30%,transparent) 6px,color-mix(in srgb,var(--line) 30%,transparent) 7px)}
.search{display:flex;align-items:center;gap:9px;font-size:12px;color:var(--muted)}
input{min-height:42px;border:1px solid var(--line);border-radius:8px;padding:9px 12px;color:var(--ink);background:var(--surface);width:240px}
.trial-detail{margin-top:9px;border:1px solid var(--line);border-radius:11px;background:var(--surface);scroll-margin-top:24px}
.trial-detail>summary{display:flex;align-items:center;gap:14px;min-height:74px;padding:14px 18px;cursor:pointer;list-style:none}
.trial-detail>summary::-webkit-details-marker{display:none}
.trial-title{flex:1;min-width:0}
.trial-title>strong{font-size:13px;font-weight:550}
.trial-title small{overflow-wrap:anywhere}
.trial-score{font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}
.expand{font-size:20px;color:var(--muted);margin-left:8px}
.trial-detail[open]>summary .expand{transform:rotate(45deg)}
.trial-body{padding:24px;border-top:1px solid var(--line)}
.evidence-columns{display:grid;grid-template-columns:1.15fr 1fr;gap:32px}
.checks{padding:0;margin:0;list-style:none}
.checks li{display:flex;align-items:flex-start;gap:10px;margin-bottom:16px}
.check-symbol{width:24px;min-width:24px;height:24px}
.checks strong{font-size:12px;font-weight:550;overflow-wrap:anywhere}
.checks p{color:var(--muted);font-size:12px;margin:3px 0}
.screenshots{display:flex;gap:12px;overflow:auto;align-items:flex-start}
.screenshots figure{margin:0;flex:1;min-width:130px;max-width:220px}
.screenshots img{width:100%;height:auto;border-radius:9px;outline:1px solid #0000001a;display:block}
.screenshots figcaption{font-size:10px;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}
.error-message{padding:12px;background:var(--error-bg);color:var(--error);border-radius:8px;margin:0 0 20px;overflow-wrap:anywhere}
.provenance,.log{margin-top:20px;border-top:1px solid var(--line);padding-top:16px}
.provenance summary,.log summary{cursor:pointer;color:var(--muted);font-size:12px;min-height:32px}
dl{display:grid;grid-template-columns:130px 1fr;font-size:12px;gap:8px}
dt{color:var(--muted)}
dd{margin:0;overflow-wrap:anywhere}
pre{background:var(--page);padding:16px;border-radius:8px;font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto}
.empty{padding:24px;color:var(--muted)}
footer{margin-top:40px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted);font-size:12px;max-width:850px}
[hidden]{display:none!important}
@media(max-width:760px){main{padding:24px 18px}
h1{font-size:30px}
.metrics{grid-template-columns:repeat(2,1fr)}
.lane-header,.section-heading{align-items:flex-start;flex-direction:column}
.lane-note{max-width:none}
.search,input{width:100%}
.evidence-columns{grid-template-columns:1fr}
.trial-detail>summary{gap:8px;padding:12px}
.trial-score{display:none}
.topline{align-items:flex-start}
.generated{max-width:160px;text-align:right}
.metric{padding:16px}
.trial-body{padding:18px}
.configuration{min-width:220px}
.attempt{width:44px;height:44px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}
}
@media print{.lane-nav,.search{display:none}
.lane-panel[hidden]{display:block!important}
.table-scroll{overflow:visible}
.trial-detail{break-inside:avoid}
main{padding:0}
body{background:white}
}

"""

SCRIPT = """
(() => {
  const tabs = [...document.querySelectorAll('[data-lane]')];
  const panels = [...document.querySelectorAll('[data-panel]')];
  function select(id) {
    tabs.forEach(t => t.setAttribute('aria-pressed', String(t.dataset.lane === id)));
    panels.forEach(p => p.hidden = p.dataset.panel !== id);
  }
  tabs.forEach(t => t.addEventListener('click', () => select(t.dataset.lane)));
  if (tabs.length) select(tabs[0].dataset.lane);
  document.querySelectorAll('[data-search-input]').forEach(input => {
    input.addEventListener('input', () => {
      const query = input.value.toLowerCase().replaceAll('-', ' ').trim();
      input.closest('[data-panel]').querySelectorAll('[data-search]').forEach(row => {
        row.hidden = !row.dataset.search.toLowerCase().includes(query);
      });
    });
  });
  function reveal() {
    const target = document.getElementById(location.hash.slice(1));
    if (!target || !target.matches('[data-detail]')) return;
    const panel = target.closest('[data-panel]');
    if (panel) select(panel.dataset.panel);
    target.hidden = false; target.open = true;
    target.scrollIntoView({block: 'start'});
    target.querySelector('summary').focus({preventScroll: true});
  }
  addEventListener('hashchange', reveal);
  document.querySelectorAll('.attempt').forEach(a => a.addEventListener('click', () => {
    const target = document.getElementById(a.hash.slice(1));
    if (target) { target.open = true; target.hidden = false; }
    setTimeout(reveal, 0);
  }));
  if (location.hash) reveal();
})();
"""


def render_report(trials, title, run_names, nav_html="", extra_html="", refresh=None, *, illustrative=False):
    lanes = defaultdict(list)
    for t in trials:
        lanes[lane_for(t)].append(t)
    panels = []
    tabs = []
    legend = '<div class="legend">' + "".join(f'<span><b class="check-symbol {s}">{SYMBOLS[s]}</b>{LABELS[s]}</span>' for s in LABELS) + '</div>'
    for lane, (label, subtitle, note) in LANES.items():
        records = lanes.get(lane, [])
        if not records:
            continue
        if any(t.agent == "calibration-control" for t in records):
            note += " Calibration controls show application outcomes: a broken baseline or distractor should fail. Check calibration.json for the complete control verdict."
        tabs.append(f'<button type="button" class="lane-tab" data-lane="{lane}" aria-pressed="false" aria-controls="lane-{lane}">{label}<span>{len(records)}</span></button>')
        counts = Counter(t.outcome for t in records)
        finished = len(records) - counts['pending']
        known_costs = [t.cost_usd for t in records if t.cost_usd is not None]
        spend = f"${sum(known_costs):.2f}" if known_costs else "—"
        output_tokens = [t.output_tokens for t in records if t.output_tokens is not None]
        usage = f"{fmt_tokens(sum(output_tokens))} output tokens" if output_tokens else "Tokens not recorded"
        cards = [
            ("Recorded outcomes", str(finished), f"{counts['pending']} pending · {len({t.task for t in records})} observed tasks"),
            ("Complete attempts", f"{counts['pass']} <span>/ {finished}</span>", "Includes execution errors in the denominator"),
            ("Execution errors", str(counts['error']), "Separate from valid failing scores"),
            ("Recorded agent spend", spend, f"{len(known_costs)}/{len(records)} records · {usage}"),
        ]
        metrics = ''.join(f'<div class="metric"><div class="metric-label">{label_}</div><div class="metric-value">{value}</div><small>{sub}</small></div>' for label_, value, sub in cards)
        detail = ''.join(render_trial(t) for t in sorted(records, key=lambda t: (t.outcome == 'pass', t.task, t.model, t.name)))
        panels.append(f'''<section class="lane-panel" id="lane-{lane}" data-panel="{lane}" aria-label="{label}">
          <div class="lane-header"><div><div class="eyebrow">{subtitle}</div><h2>{label}</h2></div><aside class="lane-note">{note}</aside></div>
          <div class="metrics">{metrics}</div>
          <div class="section-heading"><div><h3>Configuration outcomes</h3><p class="subtle">Completion first. Partial credit and execution problems remain visible.</p></div></div>
          {render_configurations(records)}
          <div class="section-heading"><div><h3>Task matrix</h3><p class="subtle">Each symbol is one attempt. Select it to inspect the checks and evidence.</p></div>
          <label class="search">Find a task<input type="search" data-search-input placeholder="Filter tasks…" aria-label="Filter {label.lower()} tasks"></label></div>
          {legend}{render_matrix(records)}
          <p class="subtle">Blank cells mean no result was recorded. Three attempts can reveal inconsistency; they do not establish a precise ranking. Compare the same task cohort and runtime.</p>
          <div class="section-heading"><div><h3>Checks &amp; evidence</h3><p class="subtle">Problems appear first. Expand an attempt for the recorded explanation.</p></div></div>{detail}
        </section>''')
    generated = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    refresh_meta = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ''
    demo = '<div class="demo">Illustrative preview · fabricated records for report design. No evaluations were run.</div>' if illustrative else ''
    empty = '<p class="empty">No recorded trial results. This report does not start evaluations.</p>' if not trials else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{refresh_meta}
      <title>{esc(title)}</title><style>{CSS}</style></head><body><main>{nav_html}
      <div class="topline"><div class="brand"><span class="brand-mark" aria-hidden="true">↗</span> EXPO / EVALUATIONS</div><span class="generated">{generated}</span></div>
      <h1>{esc(title)}</h1><p class="intro">See which tasks complete, where attempts disagree, and the evidence behind each result.</p>{demo}
      <div class="subtle">Recorded inputs: {esc(run_names)}</div>
      <nav class="lane-nav" aria-label="Measurement views">{''.join(tabs)}</nav>{empty}{''.join(panels)}{extra_html}
      <footer>Measurement views stay separate; there is no combined mobile-app score. Mean score averages valid attempt scores within each task, then across observed tasks. Completion counts fully passing attempts among recorded outcomes, including execution errors. Missing planned trials are shown separately. Agent spend and tokens include only recorded usage; judge spend and cloud compute are excluded. Calibration is not inferred from a high score. Embedded screenshots are limited to three per attempt.</footer>
      </main><script>{SCRIPT}</script></body></html>'''
