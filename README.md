# Expo Harbor Evals

Evaluate how agents **write Expo app code** and **operate mobile apps**.
Harbor runs the jobs; this repository owns the tasks, verifiers, native runners
and reports. Local execution uses a Mac. Cloud verification uses EAS Workflows.

Start with the [folder-by-folder guide](docs/repository-map.md), then
[run a small pilot and read the evidence](docs/run-and-read-evaluations.md).
The [feedback review](docs/feedback-review.md) explains the 15 reviewed reports,
the new paywall task and review tracking in the feedback MCP.
The [Sonnet effort pilot](docs/sonnet-effort-pilot.md) records subscription runs,
behavioral counterchecks and current grading weaknesses.
The [Harbor adoption guide](docs/harbor-adoption.md) covers executable paywall
grading, saved-submission regrading and the actual replay results.

## What is evaluated

| Task family | Measurement | Current coverage |
|---|---|---|
| `tasks/codegen/` | Source review; paywall also executes a policy contract | 19 tasks: 9 API exercises and 10 field-report regressions |
| The same `tasks/codegen/` tasks | Build and native UI behavior | 3 experimental iOS repair profiles |
| `tasks/simbench/` | Agent and device-tool operation of a fixed app | 10 SwiftUI simulator tasks (7 UI probes + 3 OAuth sign-in) |

There are **29 task definitions**. Native verification reuses three coding tasks;
it does not add another task family. Keep source, native and device-use scores
separate. Native profiles still require simulator calibration before their
model results can be interpreted.
The paywall task passed its initial source controls, but actual candidates
exposed source-judge false positives. The normal grader now rejects these using
executable policy checks. Existing coding comparison jobs keep their frozen
18-task cohort pending full calibration of the combined grader.

Exact-reference comparison is available as a harness smoke check. It is not
coding-quality scoring. The external mobile-result import bridge has been removed.

## Repository layout

```text
tasks/                  Benchmark inputs, hidden solutions and verifiers
  codegen/              Write or repair Expo code
  simbench/             Operate a fixed simulator app
  TRIAGE.md             Decisions about feedback reports
  feedback-reviews.json  Structured review inventory for the feedback MCP
jobs/                   Experiment configuration, grouped by measurement
  codegen/              Source judging, model comparisons and smoke checks
  native/               Build and interact with submitted Expo apps
  simbench/             Compare agents and simulator tools
src/expo_harbor_evals/   Shared Python implementation
mobile/templates/       Pinned Expo SDK runtime templates and dependency locks
suites/                 Frozen task membership and evaluator fingerprints
tests/                  Unit and consistency checks for this repository
.eas/workflows/         Cloud worker configuration
scripts/                Cloud worker entry point
docs/                   Current guides; superseded research in archive/
results/                Small, tracked history summaries
```

`runs/`, `outputs/`, `.context/`, `.venv/` and cache directories are local/generated
files, not benchmark definitions. See the [complete directory map](docs/repository-map.md)
for their purpose and the structure inside each task.

## Start without running an evaluation

```sh
uv sync --dev
# Node.js 24+ is needed for the executable paywall checks.
make check
make test

# Inspect one coding attempt and its native verifier; do not execute them.
uv run harbor run -c jobs/native/repairs.yaml \
  --path tasks/codegen \
  --include-task-name sdk-04-image-picker-canceled-assets-guard \
  --n-attempts 1 --job-name native-picker-pilot --print-config
```

These commands make no model calls and start no simulator. Bare `make` shows help.
The [pilot guide](docs/run-and-read-evaluations.md) explains calibration, the
actual run command, expected control outcomes and cost boundaries. Avoid a full
model ladder as the first test: `jobs/codegen/models.yaml` schedules 270 coding
attempts plus judging; `jobs/native/repairs.yaml` schedules 9 coding attempts
plus native verification.

Local native runs need Xcode, an iOS simulator runtime, Node, CocoaPods and the
pinned device driver. Coding agents and source judges use their own model
credentials. Scripted native calibration makes no model calls.

For EAS, copy `.env.example` to `.env.local` once and supply `EXPO_TOKEN` and
`EAS_EVAL_PROJECT_ID`. The cloud worker can verify an existing candidate or
calibrate a fixed simulator task. It does not launch a cloud coding agent.
Expo Sandbox MCP and E2B are not dependencies. See
[local and EAS setup](docs/running-mobile-evals.md).

## Read recorded results

```sh
uv run expo-eval-report runs/native-picker-pilot -o outputs/picker-report.html
make viewer  # http://127.0.0.1:4477
make export  # Append finished Harbor summaries to results/history.jsonl
```

The offline report separates measurements and shows completed attempts,
execution errors, missing results, recorded costs and a task matrix. Click an
attempt for named checks, source reasoning and available screenshots/logs.
Reporting reads existing files; it does not invoke a model or replay the app.
Standalone native candidates, native calibration and downloaded EAS evidence
use the same report command.

## Maintain the suite

Read [CONTRIBUTING.md](CONTRIBUTING.md) for task authoring and calibration rules,
and [evaluation quality](docs/evaluation-quality.md) for current coverage and
limitations. Task copies are self-contained for Harbor; sync tests keep shared
verifiers and scaffolding aligned. Review changes before refreshing the suite
with `uv run expo-eval-suite lock`.

The nine adapted API exercises are maintained here directly; no upstream checkout
or re-import command is required. Their original attribution is in [NOTICE.md](NOTICE.md).
