# Local evaluation workbench

Status: first local implementation available in `studio/`, 24 September 2026.
See [setup and implemented scope](../studio/README.md). The product direction
below includes later capabilities; it is not a claim that every slice ships.

The first version uses TanStack Start, Router, and Query, Zustand, Zod, and
Expo's shared theme/icon packages. It includes catalog/evidence views, coding
draft authoring, a shared RewardKit picker, library editing, task export, free
local controls, and Sonnet plan export. The authoring UI is one page with
expandable code and examples. Compare, the stack panel, and the footer were
removed to keep it focused. Native launch, paid dispatch, regrading, and suite
promotion remain explicit CLI/review workflows. See the [grading kit](../graders/README.md).

## Outcome

Give someone who clones this repository a local browser interface to understand
the existing evaluations, author a new one, run a small experiment, and inspect
why an attempt passed or failed. Harbor remains the runner. Task folders and
recorded evidence remain usable without the UI.

The first screen is the task library. A fresh checkout should be useful before
the user configures credentials, boots a simulator, or runs a model.

This direction follows a Safari exploration of [2027.dev](https://2027.dev/)
and its Expo workspace. Useful patterns include a short creation flow, task
scenarios, immutable executed prompts, run history, trace navigation, and
findings linked to runs. Its [documentation](https://2027.dev/evals/expo.dev/docs)
describes an agent-experience product for developer tools. The local workbench
should organize around reproducible Expo evaluation tasks and their evidence.

## What exists today

Inspection of the current checkout found:

| Existing capability | Implementation | Product implication |
|---|---|---|
| 29 definitions: 19 coding and 10 simulator-operation tasks | `tasks/codegen/`, `tasks/simbench/` | Populate a library from actual files, including tasks with no runs. |
| Three native repair profiles within those 19 coding tasks | `tests/requirements/runtime.json`, `mobile_scenarios.py` | Native verification is a capability of a coding task, not three more tasks. These profiles remain experimental. |
| One executable policy contract | Paywall `behavior.json` and `contract.cjs` | Explain precisely what runs; this is JavaScript policy behavior, not native UI verification. |
| A local, read-only run viewer | `viewer.py`, bound to `127.0.0.1:4477` | Extend an existing entry point. There is currently no task catalog, task-writing endpoint, or launch endpoint. |
| Common result reader and offline report | `report.py`, `report_view.py` | Reuse result normalization and evidence rendering. Do not introduce another scoring implementation in the UI. |
| Source, native, and simulator calibration commands | `codegen_calibrate.py`, `mobile_calibrate.py`, `simbench_calibrate.py` | Expose the appropriate checks for each task and measurement. Calibration is not a single universal button with a universal cost. |
| Saved-submission regrading | `codegen_regrade.py` | Let users check a saved answer under a revised grader without paying for another generation. Preserve the original result. |
| Task vocabulary and experiment fingerprints | `metadata.py`, `evaluation_identity.py`, `suites/mobile-v2.json` | Retain task IDs and record the actual task, evaluator, model, effort, and tool configuration. |
| Shared task file templates | `codegen_scaffold.py` | Useful building blocks for an authoring service; this module is not currently a complete task-creation CLI. |

Readiness needs care: 24 of the 29 definitions have no explicit
`validation_status`. Missing metadata must display as unknown, never as
calibrated. The paywall task requires full judge calibration, two OAuth tasks
require simulator calibration, and the Safari handoff task is held pending
driver support. Definitions, executable support, and demonstrated calibration
are different facts.

## A focused interface

Use three primary destinations: **Tasks**, **Runs**, and **Drafts**. Put local
runtime and credential availability in a small environment panel. Make
**New task** a clear action in the library.

Keep the existing viewer's restrained typography, neutral surfaces, and use of
color for status. Use a wide catalog with a task detail pane, a full-page editor
for authoring, and a split evidence view for attempts. A complex task editor
needs more room than a modal. Search and filters should preserve the selected
task and be represented in the URL.

### Tasks

Show a readable title, short purpose, task family, available measurements,
calibration status, and local run count. Filter by coding/device operation,
category, measurement, and readiness. Show a task's declared difficulty as an
author estimate, separately from observed pass rates.

Do not give an unrun task a zero score or give a task with only source results
a native pass badge. Avoid a universal leaderboard across unlike measurements.

A task detail has four sections:

- **Brief:** symptom, goal, constraints, starting files, and source motivation.
- **Checks:** named requirements, their verifier type, and the evidence needed.
- **Calibration:** known-good and known-bad controls, expected outcomes, actual
  evidence, evaluator revision, and what still needs validation.
- **Attempts:** saved runs, individual outcomes, configuration, usage, and links
  to source or simulator evidence.

Authors may inspect references and hidden verifiers in the UI. Agent execution
must continue to receive only its permitted task workspace; browsing a task
must not change those isolation boundaries.

### New task

The default entry is **Duplicate an existing task**. Provide a small set of
templates for a coding repair, an Expo API exercise, or a fixed-app operation.
Show advanced file editing alongside a guided form.

1. Describe the task: title, motivation, symptom, success behavior, and constraints.
2. Choose the starting project or fixed app and the measurement to support.
3. Define named checks. Prefer executable assertions where practical; label
   source-judge requirements explicitly.
4. Supply a correct reference and a plausible wrong fix, including the exact
   check that should reject the wrong fix. Allow alternative correct references.
5. Save a draft at any point; show missing ingredients without launching a run.
6. Validate files and run the chosen calibration controls as separate actions.
7. Review the generated file diff and add the task to the repository. Suite
   membership and lock updates are an explicit subsequent review step.

Anyone can describe and save an idea. Producing a trustworthy executable
verifier still requires engineering work; a natural-language form cannot
automatically prove correctness. Optional AI assistance can propose checks or
starter code, but generated material stays a draft until reviewed and tested.

Drafts should live outside `tasks/`, in a local draft directory, so half-written
tasks do not enter suite discovery or invalidate a frozen cohort. Promotion
produces the normal Harbor task folder, shared verifier copies, manifests,
references, and metadata. The UI must surface ignored required files before
promotion; task authoring tests already guard against this failure class.

### Run setup

Offer distinct actions: validate files, calibrate a grader, run a model,
regrade an existing answer, and export a report. Show which actions use model
tokens, judge tokens, local native builds, or EAS compute before dispatch.

The run form selects a task revision or frozen cohort, measurement, agent and
model, supported effort setting, tools/skills condition, attempts, and runtime.
Resolve inherited defaults and show the complete plan before starting. A plan
should state the number of candidate attempts and verifier executions, rather
than hiding a large experiment behind one button.

Preflight checks must distinguish missing credentials, unavailable Docker or
simulator support, stale calibration, and a held task from an ordinary model
failure. Start with one active simulator trial. The current repository already
requires isolated device IDs and conservative concurrency.

Show reported spend and its coverage. Judge spend is currently missing from
the general reporting path, and subscription CLI usage is not an invoice.
Unknown cost must remain unknown. A budget control needs enforceable adapter
limits or conservative reservations and a stop-on-missing-usage policy; a
post-run cost display alone is not a hard cap. Do not advertise a universal
hard spending cap until all dispatched chargeable paths can enforce it.

### Runs and evidence

Keep execution state separate from evaluation outcome. A process can finish
with a failed task, or fail before the task could be judged. Show cancelled,
timed-out, withheld, and missing work explicitly in planned coverage.

Open a failed attempt on its first failed check. Place the check and its
reason on the left, with relevant source, logs, screenshots, and event evidence
on the right. Keep the full trace accessible below. Every evidence link must
belong to that attempt and record its provenance.

Read existing artifacts without calling a model. AI explanations, if added
later, must be optional and separately identified. Preserve a regrade's link
to the source submission and show no new generation cost for the replay.

### Comparison (deferred from the UI)

Make paired experiments easy: same tasks, same model and tools, low versus
high effort; or the same model and effort with and without a skill. Change one
axis at a time and show the resolved configuration difference.

Use full task completion as the headline, with per-check differences, attempts,
execution errors, latency, and known usage underneath. Keep source review,
source-plus-policy, policy-only, native UI, and device operation separate.
Comparable groups need matching task/evaluator versions, measurement, and all
non-treatment conditions. Do not require identical experiment hashes across
arms: effort or skill changes are intentionally part of those hashes.

Show each repetition and the denominator before a mean. Small samples are
exploratory; withheld and failed infrastructure work are visible, not evidence
of reasoning difficulty. Do not infer that more thinking improves performance
from a single favorable pair. The retained Sonnet pilot does not establish a
reliable effort benefit; preserve that conclusion in the UI.

Task-development runs and a held-out comparison cohort should be marked
separately. A low-fail/high-pass example is a finding to replicate, not a reason
to retune the grader until it gives the desired ranking.

## Technical boundary

Retain the Python runner/reporting layer. The implemented TanStack Start app
uses a small Python bridge around the canonical result reader. The existing
read-only viewer remains available independently.
There is no need for accounts, a hosted database, or a second evaluation engine
to make this useful locally.

For authoring and launch, introduce explicit services behind the UI:

- A catalog reader normalizes task metadata and evidence availability.
- A draft writer validates inputs and produces reviewable task folders.
- A plan builder resolves a Harbor configuration without running it.
- A job controller launches the existing commands, records ownership and
  lifecycle, polls logs, and cancels its owned process tree, including detached
  descendants created by the local environment adapter.

Persist a run's plan and ownership before launch; recover interrupted state
after a server restart. Do not infer process liveness from file modification
time alone once the UI owns job execution. Keep only lightweight local state;
definitions and completed evidence stay in the existing file formats.

Adding write/run endpoints changes the current viewer's trust boundary. Keep
loopback binding, validate hostnames and same-origin CSRF metadata for server functions,
constrain paths including symlinks, and use structured process arguments.
Only launch explicitly reviewed local task code. Preserve the candidate and
verifier sandbox separation. Credential values stay in the existing local
credential stores or environment, with only availability shown in the UI.

The current suite fingerprint excludes four presentation modules by filename.
New UI-only code must not accidentally become evaluator identity, while new
execution-affecting code must be fingerprinted. Make that distinction explicit
when adding modules rather than excluding a whole mixed-purpose directory.

“Everyone” initially means contributors can clone the repo, browse definitions,
save drafts, and share reviewed changes through Git. Running on their machines
uses their credentials and runtime. A shared multi-user server would be a
separate product scope with authentication and isolated execution.

## Implementation slices and acceptance

| Slice | Deliverable | Acceptance |
|---|---|---|
| 1. Browse | Task library, task details, links to recorded attempts | A fresh clone with no `runs/` shows all 29 definitions; filters work; unknown, held, and experimental states stay visible; no model or simulator starts. |
| 2. Author | Duplicate/template flow, resumable drafts, checks editor, file diff | Saving starts no evaluation; drafts stay outside the suite; generated tasks satisfy repository authoring and sync checks; missing controls prevent a calibrated badge. |
| 3. Validate and run | Calibration selection, plan preview, local preflight, job controller | Correct/broken controls are assessed for their intended reasons; errors remain errors; cancellation and restart are handled; usage gaps stop guarded dispatch. |
| 4. Compare and contribute | Paired plan, evidence comparison, exportable task/result bundles | Both arms retain their full planned coverage and configuration; incompatible measurements/revisions cannot be silently pooled; references and secrets are not supplied to candidate runs. |

The first vertical slice should be **browse a real task → inspect its checks →
open a recorded failure → duplicate it into a local draft**. Use the paywall
task to demonstrate source versus policy evidence and the held Safari task to
demonstrate honest readiness. Add actual execution after that flow is useful.

Defer automated insight generation, an AI chat sidebar, hosted schedules,
competitor-provider rankings, and GitHub App installation. They add little to
the initial local authoring and evidence loop. Later, a failure can seed a
draft task with its source evidence attached; it should not silently become a
published regression or automatically submit a PR.

## Exploration limits

The Safari exploration covered the dashboard, catalog, new-prompt form,
scaffolds, task overview, scenarios, run configuration, recorded run selection,
comparison setup, a trace, verifier checklist, insights, and documentation.
The supplied screenshots also showed the benchmark and unconnected PR pages.
No task was submitted, scheduled run started, integration connected, or
comparison analysis requested. Backend correctness and 2027's grader accuracy
were not tested. Its public OpenAPI contract documents custom verifier checks
as scoring-model inputs; that observation does not establish how every default
check is implemented.

This proposal is grounded in repository inspection, not a new calibration run.
See [evaluation quality](evaluation-quality.md), [authoring rules](../CONTRIBUTING.md),
and the [Sonnet pilot](sonnet-effort-pilot.md) for the current evidence and limits.
