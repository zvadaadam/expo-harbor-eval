# One-attempt pilot for the new feedback tasks

This is a small source-review diagnostic, not a mobile runtime benchmark or a
statistical model ranking. It selects only `feedback-12` (native amount-column
layout) and `feedback-13` (authentication render path and field sizing).

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
a passing result. Once the controls pass, this starts the four agent attempts:

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
