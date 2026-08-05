# Expo Harbor Evals

Standalone Harbor tasks and utilities for Expo and React Native agent evals.

This repo intentionally **does not fork Harbor**. Harbor remains the eval runner:
jobs, trials, agents, logs, reward aggregation, and result viewing. This repo owns
the Expo-specific task definitions and the small adapter that turns an Expo
`eval-out/result.json` into Harbor's numeric `/logs/verifier/reward.json`.

## Why Not Fork Harbor?

Fork Harbor only when the core framework has to change. For this work, Harbor's
existing contract is enough:

1. A task has `instruction.md`, `task.toml`, `environment/`, and `tests/test.sh`.
2. Harbor runs `tests/test.sh`.
3. Harbor reads `/logs/verifier/reward.json`.

The iOS simulator/EAS workflow should be a producer of evaluator `result.json`,
not a new Harbor data model.

## Repository Shape

```text
jobs/                         Harbor job configs
src/expo_harbor_evals/        Development helpers
tasks/expo-mobile-eval-import Harbor task that normalizes evaluator output
tasks/expo-{sdk,router,ui}-*   expo-codegen: imported RN code-generation tasks
tasks/expo-feedback-*          expo-codegen: tasks authored from field feedback
third_party/                   Upstream license and pinned-source metadata
```

## Expo code-gen tasks (expo-codegen)

The repo includes an importer for selected tasks from
[`callstackincubator/evals`](https://github.com/callstackincubator/evals). The
default cohort contains nine Expo tasks across `expo-sdk`, `expo-router`, and
`expo-ui`:

```bash
make codegen-import
```

Each upstream eval becomes a normal Harbor task. The prompt and baseline app are
the agent input, the reference implementation becomes the Harbor oracle, and
the weighted requirements become a provider-neutral Rewardkit rubric.

Run every oracle solution without Docker or API keys:

```bash
make codegen-oracle
```

This uses exact reference comparison only as an import/plumbing smoke test. It
is intentionally separate from real scoring because valid agent solutions do
not need to match the reference source text.

For an LLM-judged run without a coding agent, score the untouched baseline
(`nop`) against the reference solution (`oracle`) across every expo-codegen
task:

```bash
# Default judge: the logged-in claude CLI (claude-code · claude-opus-4-8).
make codegen-judge
# Hosted LiteLLM judges need an explicit id plus their provider key:
REWARDKIT_JUDGE=anthropic/claude-sonnet-4-6 make codegen-judge
REWARDKIT_JUDGE=openai/gpt-5.2 make codegen-judge
```

Judge-mode rewards land under Harbor's conventional `reward` key, same as
reference mode, so results are comparable across modes.

Two deterministic guards run before any judge call: an empty workspace, or one
byte-identical to the imported baseline (per the task's
`baseline-manifest.json`), scores 0 without invoking a judge. That keeps
negatively-phrased criteria from passing vacuously on absent code and keeps a
misfiring judge from rewarding a no-op. `make codegen-calibrate` asserts all
three brackets per task — empty → 0, unchanged baseline → 0 (both guard-only),
reference → 1.0 (judged) — plus, for tasks that ship a `solution/distractor/`,
a judged plausible-but-wrong solution that must score below 1.0. Rerun it
after any rubric, judge-prompt, or runner change (`--only <task-dir-name>`
scopes it to the task being authored).

To compare agent models and reasoning-effort levels using the host's
logged-in claude CLI (dev-only, host-executed — see
`expo_harbor_evals.claude_host_agent`):

```bash
make codegen-models     # haiku/sonnet/opus/fable @ low effort + haiku @ high
make report             # merged HTML report in outputs/eval-report.html
```

Both judged jobs run 3 attempts per task/config and pin the judge to
`claude-code · claude-opus-4-8` so runs are comparable. On macOS they execute
inside `expo_harbor_evals.mac_sandbox_env:MacSandboxEnvironment`, a
seatbelt (`sandbox-exec`) wrapper over the local environment that denies
writes outside the trial root — the pragmatic sandbox for mobile-native evals
that can't live in Linux containers (iOS simulators, EAS, Xcode). VM-level
isolation (e.g. Tart) remains the CI-grade option.

For a real agent run, use the normal `judge` verifier mode and pass a LiteLLM
judge plus its provider credential. For example:

```bash
uv run harbor run \
  --path tasks \
  --include-task-name 'expo-sdk-*' \
  --include-task-name 'expo-router-*' \
  --include-task-name 'expo-ui-*' \
  --include-task-name 'expo-feedback-*' \
  --agent codex \
  --model YOUR_AGENT_MODEL \
  --verifier-env REWARDKIT_JUDGE=YOUR_LITELLM_JUDGE \
  --verifier-env OPENAI_API_KEY="$OPENAI_API_KEY" \
  --yes
```

The imported tasks preserve upstream requirement IDs, descriptions, weights,
commit provenance, and MIT attribution. Use `--all-expo` with
`expo-codegen-import` when the first cohort is stable enough to expand from 9
to all upstream Expo tasks.

### Field-sourced tasks (`expo-feedback-*`)

Alongside the imported cohort, `expo-feedback-*` tasks are authored from real
failure reports submitted against the Expo agent skills
(`task.toml [metadata] feedback_id` cites the report). They exist because
field reports surface the highest-signal eval shape there is: **traps**, where
the popular guidance is itself the wrong answer, so an agent that
pattern-matches best practices fails and an agent that reasons about the
actual bug passes.

Each feedback task ships three artifacts:

- `environment/` reproduces the reported setup — the baseline already follows
  the misleading guidance;
- `solution/reference/` is the correct fix;
- `solution/distractor/` is the plausible-but-wrong fix (ideally one the
  report tested and found insufficient). `make codegen-calibrate` asserts the
  judge scores it below 1.0, so the task provably discriminates instead of
  rewarding anything that looks considered.

`tasks/expo-feedback-01-transparent-header-content-inset` is the pattern's
first instance: under a transparent large-title header,
`contentInsetAdjustmentBehavior="automatic"` (the guidance) applies no top
inset on a cold launch, and the fix is explicit `useHeaderHeight()` /
`useSafeAreaInsets()` content padding. When a skill's guidance changes in
response to feedback, the matching task doubles as the regression eval for
that change.

## Simulator-Use Benchmark (simbench)

`tasks/simbench-*` prototypes a benchmark for how well model × driver-tool
stacks operate a real iOS simulator. The design inverts the app evals above:
the app is a fixed, known-good "golden app" and the driver stack is the
variable.

- **Golden app**: a single-file SwiftUI app (`environment/app-src/`) built
  with `swiftc` in seconds — no Xcode project. It journals every UI-driven
  mutation to an events file, so state injected without using the UI scores
  zero.
- **Verification**: programmatic app-state reading (`tests/verify.py`), no
  LLM judge.
- **Floor/ceiling**: the `nop` agent proves the verifier gives nothing away;
  a scripted agent-device oracle (`solution/oracle.py`) proves the task is
  completable through the UI. Model scores are only meaningful between those.
- **Per-trial hygiene**: the task healthcheck reinstalls the app fresh each
  trial; trials run with `n_concurrent_trials: 1` because the simulator is
  shared host state.

```bash
make simbench-ladder   # 3 tiers x haiku/sonnet x agent-device/argent + brackets
make simbench-hard     # failure-hunting tiers: dial precision, async, vision
```

The tasks are tool-neutral: each driver stack is an agent config whose preface
documents its tool (see `jobs/simbench-ladder.yaml` — agent-device's ref-based CLI
vs argent's coordinate-based tool-server), tagged into results via
`model_name: "sonnet#<tool>"`. Adding Maestro MCP, XcodeBuild MCP, raw
simctl+screenshots, or remote services means adding agent configs, not new
tasks.

## Eval Viewer

A local website over `runs/` that parses every eval and shows live progress —
pages rebuild from disk on each request and auto-refresh while a run is
active:

```bash
make viewer   # http://127.0.0.1:4477
```

The index lists every run with status (running / stopped / finished), trial
counts, and mean reward per configuration; each run page embeds the full
report plus a trial list; each trial page shows rewards, verifier evidence,
judge criteria with reasoning (judged runs), agent cost/turns, and the
agent's final message. Static one-off reports remain available via
`make report` / `expo-eval-report`.

## Local Smoke Without Docker

This machine did not have Docker available during the spike, so the repo includes
a tiny dev-only Harbor environment:

```text
expo_harbor_evals.local_env:LocalHostEnvironment
```

It maps Harbor paths (`/logs`, `/tests`, `/solution`, `/app`) into a per-trial
host directory. It is not a sandbox.

From this repo (Harbor is a locked dependency; add
`HARBOR_WITH="--with ../harbor"` only to develop against a local checkout):

```bash
make fixture
```

Expected: one trial, zero exceptions, `reward=1.0`.

Partial-score smoke:

```bash
make partial
```

Expected: one trial, zero exceptions, `reward=0.5`.

Note: Harbor's default output directory is literally `jobs/`, which this repo
uses for job configs. The configs set `jobs_dir: runs`, and stray output from
ad-hoc `harbor run`/`harbor check` invocations is gitignored via `jobs/*/`.

## Docker/Real Harbor Shape

On a machine with Docker:

```bash
uvx harbor run \
  --path tasks \
  --include-task-name expo-mobile-eval-import \
  --agent nop \
  --env docker \
  --yes
```

## EAS Bridge Direction

Keep EAS/macOS/iOS simulator execution outside Harbor's core. Feed the resulting
`eval-out/result.json` into the same scorer:

```bash
uv run expo-eval-score eval-out/result.json reward.json --details details.json
```

Inside Harbor, set `EVAL_RESULT_PATH` or make `MOBILE_EVAL_COMMAND` produce
`/logs/verifier/mobile-eval/result.json`.
