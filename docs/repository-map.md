# Repository map

There are two task families and three useful measurements. A coding task can be
judged from source, and some can also be built and checked on a simulator.
Simulator-operation tasks keep the app fixed and evaluate the agent using it.
Local versus EAS is where a check runs, not a separate task family.

## Every directory at the root

| Directory | Purpose | What belongs here |
|---|---|---|
| `tasks/` | Benchmark definitions | Prompts, baseline apps, hidden reference fixes and verifiers; currently 29 tasks |
| `jobs/` | Experiment plans | Which tasks, agents, models, attempts and verifier mode to run |
| `src/expo_harbor_evals/` | Implementation | Shared runners, calibration, environment adapters, scoring and reporting code |
| `mobile/templates/` | Native app scaffolding | Pinned SDK 54 and SDK 56 Expo project shells, fixture image and npm locks; candidate code is copied into these for native verification |
| `suites/` | Reproducibility | `mobile-v2.json` records task and execution/scoring fingerprints; it is not an evaluation result |
| `tests/` | Repository checks | Python unit tests and consistency checks; these do not run model evaluations or native apps |
| `.eas/workflows/` | Cloud orchestration | The macOS worker definition; its `simbench.yml` currently supports both fixed-app calibration and candidate verification |
| `scripts/` | Worker entry point | `eas_simbench.py` validates the prepared source manifest and invokes the appropriate evaluator on the EAS worker |
| `docs/` | Current documentation | Run instructions, evaluation quality and this map; `archive/` contains superseded research |
| `results/` | Committed history | Small finished-run summaries in `history.jsonl`; no raw simulator bundles |
| `runs/` | Generated raw evidence | One directory per job, containing attempts, submitted code, logs, results and evidence; gitignored |
| `outputs/` | Generated presentations | Offline HTML reports derived from existing runs; gitignored |
| `.context/` | Local working notes | Research downloads, prepared payloads and illustrative previews; gitignored by the workspace |
| `.claude/skills/` | Contributor workflow | The signal-triage instructions for deciding which feedback should become an eval; not supplied as a benchmark task |
| `.venv/` | Python dependencies | The local environment installed by `uv`; generated and gitignored |
| `.pytest_cache/`, `__pycache__/` | Tool caches | Disposable Python/pytest caches; generated and gitignored |

`.git` is a worktree pointer in this checkout, not an app folder. At the root,
`pyproject.toml` defines the Python package and commands, `uv.lock` pins dependencies,
and `Makefile` provides shortcuts. `.env.example` documents the two EAS settings;
`.env.local` holds local values and is not committed. `NOTICE.md` retains attribution
for the existing adapted API exercises.

Raw runs, rendered reports and history are deliberately different: a report can
be regenerated, while the raw evidence explains what happened. Existing recorded
runs are preserved even when a task or job is retired.

## How tasks are separated

| Location | Agent's job | Verification |
|---|---|---|
| `tasks/codegen/feedback-*` | Repair a bug drawn from a field report | Source rubric; native checks for modal handoff and slider recenter |
| `tasks/codegen/sdk-*` | Use an Expo SDK API correctly | Source rubric; native checks for the image picker |
| `tasks/codegen/router-*` | Implement a routing contract | Source rubric |
| `tasks/codegen/ui-*` | Implement an Expo UI contract | Source rubric |
| `tasks/simbench/simbench-ios-*` | Complete a UI task in a fixed SwiftUI app | App state plus the UI-event journal |

`feedback`, `sdk`, `router` and `ui` are categories within coding. They belong
together because the agent edits code and uses the same Harbor task contract.
Task IDs remain unchanged so existing results can still be matched to them.
The missing `feedback-07` number is intentional: that report is still planned
in `tasks/TRIAGE.md`, not an implemented task.
`tasks/feedback-reviews.json` is the structured companion for the current MCP
review batch; it includes covered, held and dropped findings. The new paywall
task is authored but outside existing 18-task source comparison cohorts pending
judge calibration. See [the feedback review](feedback-review.md).

The ten simbench tasks cover note creation, scrolling, an occluded form,
exact-value adjustment, waiting for an asynchronous reveal, visual selection,
an ordered multi-screen flow, and three OAuth sign-in surfaces (embedded
WKWebView, system ASWebAuthenticationSession, Safari hand-off). They are useful
device-tool probes. They do not establish the quality of generated Expo
applications. The OAuth tier is documented in [oauth-simbench.md](oauth-simbench.md).

### Inside a coding task

```text
task-name/
  instruction.md                The request the coding agent receives
  task.toml                     Harbor settings and task metadata
  environment/                  Baseline workspace the agent edits
  solution/
    solve.sh                    Copies the reference for the oracle control
    reference/                  A correct implementation
    distractor/                 A plausible wrong fix, where supplied
    reference-alternative/      Another valid design, where supplied
  tests/
    test.sh                     Chooses source, native or reference-smoke mode
    run_rewardkit.py            Shared source judge runner, copied for portability
    reference_check.py          Exact-reference smoke check
    reference/                  Hidden verifier copy of the reference
    requirements/
      rubric.toml               Acceptance criteria
      judge-prompt.md           Instructions for source judging
      baseline-manifest.json    Detects an untouched or empty submission
      calibration.json          Expected outcomes of reference/broken controls
      runtime.json              Native scenario selector, only where supported
    contract.cjs                Executable candidate policy checks (paywall)
```

The two reference directories serve different Harbor roles: the oracle needs
`solution/`, while the verifier receives `tests/`. Shared script copies also let
Harbor execute a task without importing the repository from inside its workspace.
Consistency tests enforce that these copies agree. They should not evolve as
independent implementations.

### Inside a simulator-operation task

`environment/app-src/` contains the fixed SwiftUI app. `environment/driver/`
contains trusted setup and interaction helpers. `solution/oracle.py` completes
the task through the UI as a control. `tests/verify.py` checks recorded state and
event order; the shared `simbench_evidence.py` handles evidence collection.

## Job groups

| Group | Files | Purpose |
|---|---|---|
| `jobs/codegen/` | `baseline-smoke.yaml`, `reference-smoke.yaml` | Test the harness with no-op/reference controls; no LLM or native builds |
| `jobs/codegen/` | `judge.yaml` | Judge baseline/reference controls; uses judge tokens |
| `jobs/codegen/` | `models.yaml`, `muse.yaml` | Generate candidate code and judge it |
| `jobs/native/` | `repairs.yaml` | Generate code for the three supported tasks, then build and drive each candidate |
| `jobs/simbench/` | `ladder.yaml`, `hard.yaml`, `flows.yaml`, `oauth.yaml`, `muse.yaml` | Compare models and device tools on fixed apps |
| `jobs/simbench/` | `unguided.yaml` | Test tool discovery without driver instructions; installed tools remain available |

All configs write their results to `runs/`. Run commands from the repository root.
`make simbench-unguided` replaces the misleading `simbench-notool` name. Existing
`make codegen-oracle` and `make codegen-baseline` shortcuts now point to explicitly
named smoke configs. There are no `fixture`, `partial` or upstream import targets.

## Shared implementation

| Module group under `src/expo_harbor_evals/` | Responsibility |
|---|---|
| `codegen_*` | Shared task scaffolding, source judging, reference smoke checks and source calibration |
| `mobile_*` | Prepare candidate source, build the app, run native scenarios and calibrate controls |
| `simbench_*` | Own each simulator, collect state/evidence and calibrate the fixed-app tasks |
| `eas_runner.py` | Prepare, submit, collect and cancel EAS worker runs |
| `local_env.py`, `mac_sandbox_env.py` | Harbor workspace adapters and local access restrictions |
| `claude_host_agent.py`, `muse_host_agent.py` | Host coding-agent integrations and usage accounting |
| `metadata.py`, `evaluation_identity.py` | Task vocabulary, suite locks and experiment identity |
| `report.py`, `report_view.py`, `viewer.py`, `export.py` | Read results, render reports, browse local runs and export history |

## Removed pieces

`tasks/expo-mobile-eval-import` accepted externally produced JSON and normalized
its numbers into Harbor rewards. It did not build an app, drive a simulator or
evaluate an agent. Its task, sample-result jobs, scorer/import commands and
associated code have been removed. EAS execution still uses the native and
simbench evaluators directly and keeps their complete evidence.

The old `third_party/` directory contained a license and upstream metadata, not
an installed service. Those notices are consolidated in `NOTICE.md`. The nine
adapted API exercises remain useful local tasks; upstream re-import code,
generator markers and duplicate upstream requirement files have been removed.
The task rubrics and `task.toml` metadata are now the maintained definitions.

## Where new work belongs

For another coding bug, add a task under `tasks/codegen/` after recording its
feedback decision in `tasks/TRIAGE.md`. If its behavior can be tested natively,
add a runtime scenario for that same task. For a new device-operation capability,
add a fixed-app task under `tasks/simbench/`. A new cloud transport belongs in the
runner implementation and `.eas/`, not in `tasks/`.

The structure now matches these responsibilities. The remaining quality gaps are
coverage and calibration: eight API exercises need stronger wrong-fix controls;
the three native profiles remain experimental; Android and data-dependent app
journeys need executable checks before making broader capability claims.

## Validation

The suite lock covers 29 tasks, including paywall and the three GoldenGate
OAuth tasks. The pre-merge review passed 131 offline tests, the suite lock
check, and Swift typechecking for the shared GoldenGate app. It also repeated
all six paywall policy controls and regraded a retained Sonnet submission
through Harbor; no new model calls were made.

See [Harbor adoption](harbor-adoption.md) for the recorded runs and
[OAuth calibration](oauth-simbench.md) for the live simulator checks still
required before publishing model comparisons. Syntax and evidence tests do
not establish native UI correctness.
