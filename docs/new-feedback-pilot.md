# One-attempt pilot for the new feedback tasks

This is a small source-review diagnostic, not a mobile runtime benchmark or a
statistical model ranking. It selects only `feedback-12` (native amount-column
layout) and `feedback-13` (authentication render path and field sizing).

## Observed September 14, 2026

**Do not merge as validated evals yet.** The four requested agent attempts
finished in 4m 41s with no retries or execution errors. The judge gave every
candidate 1.0, but one of those grades is a demonstrated false positive.

| New task | Haiku 4.5 patch inspection | Sonnet 5 patch inspection |
|---|---|---|
| Fixed amount column | Missed the fix: only added single-line text; the broken amount styles are unchanged | Removed shared positive flex and fixed the amount width; source supports the repair |
| Auth field render path | Fixed the actual auth form's frame and removed outer vertical padding | Produced the same patch as Haiku |

These are source-inspection findings, not replacement benchmark scores or native
runtime results. Candidate patches and all criterion reasoning are retained in
[the pilot evidence](../results/pilots/2026-09-14-new-feedback.json), which pins
the evaluated commit, task hashes, models and usage. Task metadata was updated
afterward to record the failures; the evaluated prompts, rubrics and app fixtures
were not changed or re-run after observing results.

The original, single-pass calibration is retained:

| Control | Amount column | Auth fields |
|---|---|---|
| Empty / unchanged guards | Both 0, expected | Both 0, expected |
| Reference / valid alternative | Both 1.0, expected | Both 1.0, expected |
| Commented baseline | **1.0, failed calibration** | 0.75, expected height failure |
| Wrong fix | 0.5, expected layout failure | **0.5, failed calibration**: height and Settings failed, but the required render-path failure was credited |

The layout judge applied web-style shorthand reasoning to the broken baseline
and Haiku candidate, while correctly identifying the same Yoga conflict in the
distractor. A stronger model alone is not an adequate grading strategy for this
task: make the critical geometry check deterministic against actual submitted
native layout. The auth rubric overlaps render-path correctness and corrected
layout, allowing credit for merely finding the existing auth fields. Combine
those overlapping criteria into a requirement that the *rendered* fields have
the corrected layout, then calibrate that revised definition separately. Neither
original failure was retried or discarded.

Both task cards now show **Calibration failed**. Reports and history keep these
grades under `source-unvalidated`, with the original calibration bound to task,
suite and judge identity. Per-attempt source-inspection notes and candidate
patches appear above the original judge reasoning. This prevents the recorded
four full-credit grades from being presented as validated benchmark passes.

CLI API-equivalent usage was **$0.240849 for agents**, **$0.404207 for candidate
judges**, and **$0.777804 for calibration**: **$1.422860 for the pilot and controls**.
The three independent Sonnet code reviews used another **$4.672759**. These are
Claude Code's usage estimates on the existing Max login, not evidence of an
additional bill. The logs contain only Haiku 4.5 and Sonnet 5 model usage; Claude
Code also used Haiku for auxiliary requests during Sonnet sessions.

## Reproducing the configuration

The commands below start a new evaluation and spend tokens. The dated run has
already completed; inspecting its existing report or evidence does not repeat it.

The checked-in `jobs/codegen/new-feedback-pilot.yaml` uses the host's logged-in
Claude Code subscription: Haiku 4.5 (`claude-haiku-4-5-20251001`, no effort flag)
and Sonnet 5 (`claude-sonnet-5`, medium effort). Sonnet 5 at medium effort is the
source judge for both. There are **four agent attempts**, one per task/model,
with Harbor retries disabled. The pinned Rewardkit adapter also makes only one
judge attempt; malformed answers or judge execution errors stay errors.

Use Claude Code 2.1.268 or later, `uv sync --dev`, and `claude auth status` to
check login. The pilot uses macOS `sandbox-exec` and a copy of each starting app.
It does not need an Expo token, EAS project, simulator, Docker or Sandbox MCP.
The coding agent has file editing tools; the judge has only Read/Glob/Grep.
Both exclude personal settings, skills, hooks, memory and MCP servers while
retaining subscription authentication. This measures the clean coding harness,
not an Expo-skill-assisted configuration. No fallback model is configured.

Inspect the plan before running:

```sh
uv run expo-eval-suite check
uv run harbor run -c jobs/codegen/new-feedback-pilot.yaml \
  --job-name new-feedback-pilot-2026-09-14 --print-config
```

Calibrate the two tasks first, once per control. This makes eight judged control
calls (reference, alternative, commented baseline and distractor for each task)
plus four deterministic guard checks. The artifact directory must be new;
existing evidence cannot be overwritten accidentally.

```sh
REWARDKIT_JUDGE=claude-code REWARDKIT_MODEL=claude-sonnet-5 \
REWARDKIT_REASONING_EFFORT=medium \
uv run expo-codegen-calibrate \
  --only feedback-12-native-fixed-amount-column \
  --only feedback-13-auth-field-render-path --jobs 2 \
  --artifacts outputs/new-feedback-calibration-2026-09-14 \
  --output outputs/new-feedback-calibration-2026-09-14/summary.json
```

If a control fails, inspect its named criteria and evidence before interpreting
model scores. Do not automatically repeat calibration or model attempts to get
a passing result. The dated pilot deliberately completed the four requested
diagnostic samples despite failed calibration; it remains unvalidated. For a
validated pilot, establish working controls first. This starts four attempts:

```sh
uv run harbor run -c jobs/codegen/new-feedback-pilot.yaml \
  --job-name new-feedback-pilot-2026-09-14 --yes
uv run expo-eval-report runs/new-feedback-pilot-2026-09-14 \
  -o outputs/new-feedback-pilot-report.html
uv run expo-eval-export runs/new-feedback-pilot-2026-09-14
uv run expo-eval-viewer --port 55170
```

Inspect the submitted app retained under each trial's `_local_env/app`, named
criteria under `verifier/reward-details.json`, and the actual served models in
`agent/claude-host.json` and `verifier/judge-cli.json`. CLI `total_cost_usd` is an
API-equivalent usage figure; it is not evidence of an additional subscription
charge. Main reports/history currently total **agent usage only**; retained judge
logs allow judge usage to be accounted for separately. Report review costs,
calibration costs and candidate-scoring costs separately from agent attempts.

No source score establishes that either app builds or renders correctly on a
device. The offline React/Yoga controls are separate authoring checks. A single
pass or failure is useful diagnostic evidence, not a success-rate estimate.
