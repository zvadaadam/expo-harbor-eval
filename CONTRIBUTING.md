# Contributing

This repo packages Expo agent evals on top of Harbor. Two families live in
`tasks/`: expo-codegen under `tasks/codegen/` (API exercises and field-report
regressions), and simbench under `tasks/simbench/` (operating fixed apps).
Coding tasks support source review; three also support experimental native
verification. Jobs are grouped under `jobs/codegen/`, `jobs/native/` and
`jobs/simbench/`, and explicitly select their cohort. Suite definitions are
versioned in `suites/mobile-v2.json`. Simbench task dirs keep their
`simbench-ios-` prefix: the dir name is the Harbor task name, and those names
are the join keys for existing run data — renaming them would orphan it.
Adding to any family, keep the rules below — they are what make the numbers
trustworthy.

Use [the repository map](docs/repository-map.md) to place new work. Shared coding
task templates live in `src/expo_harbor_evals/codegen_scaffold.py`; update their
task copies together. The tasks are maintained locally, without re-importing
an upstream repository. Preserve attribution in `NOTICE.md` and task metadata.

## Scorer discipline

- **Score what the agent produced, never what the harness provisioned.** If
  setup installs the app or seeds state, checks must only credit deltas the
  agent made on top.
- **Prefer programmatic verification over LLM judges.** Simbench verifiers
  read app state from the simulator container; a judge is a last resort and
  must be pinned (`REWARDKIT_MODEL`).
- **Emit named checks.** Verifiers return `checks: [{name, passed, notes}]`
  in `details.json` and derive the reward from them, so a failing trial
  explains itself in the viewer.
- **Defeat state injection.** Golden apps journal every UI-driven mutation;
  a state change without its matching journal event scores zero.

## Calibration is mandatory

Every task ships both brackets, and both must pass before a model number
means anything:

- a **no-op floor**: the `nop` agent must score 0 (the verifier gives nothing
  away), and
- a **scripted oracle ceiling**: `solution/` completes the task through the
  UI (or reference solution) without an LLM and must score 1.0.

If the oracle cannot reach 1.0 deterministically, fix the task or the
verifier — do not ship it.

For the expo-codegen family, calibration checks empty and unchanged guards,
then sends a commented baseline through the real judge. Declare its missing
behaviors in `tests/requirements/calibration.json`. Every reference criterion
must pass; each distractor must fail the particular criterion it breaks.
An unrelated deduction does not establish that the judge recognizes the bug.
Supply alternative valid references when the rubric allows different designs.
Rerun calibration after changing task behavior, criteria, prompts or the judge.

The native lane is opt-in and experimental. `expo-mobile-calibrate` requires
complete references to build and pass all native checks, while baselines and
applicable distractors must build and fail UI assertions. An infrastructure or
compilation failure cannot establish a negative control. Follow
[the native guide](docs/evaluation-quality.md) before interpreting its scores.
Do not label a task calibrated based only on source review or unit tests.

## Field-sourced tasks (feedback-*)

`tasks/codegen/feedback-*` tasks turn real failure reports about the Expo agent skills
into regression evals. The best candidates are **traps**: setups where the
popular guidance produces the wrong answer, because they separate agents that
reason about the bug from agents that pattern-match best practices. Rules:

- **Cite the source.** `metadata.motivation` describes the report and
  `metadata.feedback_id` carries its id; the task must be traceable to the
  field signal that motivated it.
- **The baseline follows the misleading guidance.** `environment/` reproduces
  the reported setup so the agent starts from the code the guidance produces,
  not from a strawman.
- **Give the symptom, not the diagnosis.** The instruction reads like the bug
  report (what the user saw, when) and never names the root cause or the API
  to use — that is the thing being evaluated.
- **Pin the product requirements.** State explicitly which parts of the setup
  must stay (the transparent header, the search bar, …) so the cheap escape —
  deleting the feature that triggers the bug — is a rubric failure, not a win.
- **Ship the wrong fix.** `solution/distractor/` holds the plausible-but-wrong
  solution, ideally one the report tested and found insufficient; calibration
  asserts it judges below 1.0.

## Task metadata

`task.toml [metadata]` uses the controlled vocabulary in
`src/expo_harbor_evals/metadata.py` (enforced by `tests/test_metadata.py`):
`family`, `category`, `tier`, `difficulty`, plus a required `motivation` —
the link, ticket, or thread that says why the task exists.

## Benchmark hygiene

- Review suite membership and refresh `expo-eval-suite lock` deliberately after
  a task or evaluator change. Never pool source-review and native UI scores.
- Repeat trials (`n_attempts: 2+`) before comparing configurations; simulator
  and judge runs are stochastic.
- One variable per axis: same model across tools to compare tools, same tool
  across models to compare models. Tag configurations via
  `model_name: "<model>[@effort][#variant]"`.
- Ship paired variants for prompt/skill A/Bs (e.g. `#argent` vs
  `#argent-nodocs`) rather than editing a config in place.
- Simbench jobs use `SimbenchEnvironment` and explicit per-trial device IDs.
  Keep `n_concurrent_trials: 1` until resource capacity is measured; tasks
  install their golden app per trial via the healthcheck. Never select an
  arbitrary `booted` simulator or close another trial's tool session.
- Simbench verifiers share the vendored `simbench_evidence.py` collector.
  Update the source and all task copies together; the sync test guards drift.
  Keep task checks independent of local/remote evidence transport.
- Tasks sharing a golden app must ship byte-identical app sources
  (`tests/test_task_sync.py`).

## Simbench task shape: probes today, flows next

The current simbench tiers are deliberately atomic capability probes — each
isolates one thing a driver stack can fail at (scroll, occlusion, exact-value
adjustment, async, vision). Keep authoring those for new failure classes, but
the next tier is **flows**: 5+ dependent steps in one golden app (create →
edit → organize → search), because atomic device-use tasks saturate for good
stacks (AppControlBench's top cell completes 97.5% of its 60 real-app tasks)
while errors compound over flows. Rules for flow tasks:

- **Verify the sequence, not just the end state.** The golden-app journal
  must show the steps happened in order through the UI; a correct final
  state reached out of order (or injected) scores zero. This is the
  advantage over screenshot-judged benchmarks — a final screenshot cannot
  grade a flow.
- **Pair every flow with its atomic probes** so a flow failure localizes to
  a capability instead of a shrug.
- **Name conditions honestly.** `jobs/simbench/unguided.yaml` is an unguided
  condition: the tools remain installed. A true no-tool comparison requires
  enforcing a restricted tool surface, not merely changing the preface.

Real production apps as surfaces (AppControlBench uses frozen Bluesky and
Element builds) come after flows, as their own task family. When they do:
pin every surface in a frozen manifest (version + upstream commit of the
installed build), have the harness warn on drift, and prefer server-state
verification (Matrix API, ATProto PDS, Immich server) over screenshot
judging — a real app you cannot verify programmatically is a demo, not an
eval.

## Results over time

After a finished run: `make export` appends a summary row to
`results/history.jsonl` (tracked in git); the viewer's History section renders
it. Export before changing prompts, tools, or models so regressions are
attributable.

Token usage and cost are part of the results, not telemetry to discard: every
agent must populate Harbor's `AgentContext` usage fields (`n_input_tokens`,
`n_cache_tokens`, `n_output_tokens`, `cost_usd` — `ClaudeHostAgent` reads them
from the claude CLI envelope), and the report, viewer, and history export carry
per-series and per-run totals. Absent usage exports as `null`, never a fake 0.
Known gap: judge spend (harbor-rewardkit) is not reported upstream and is
excluded from all totals.
