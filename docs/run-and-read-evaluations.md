# Run a small pilot, then read the evidence

Nothing in this guide has been executed as an evaluation during the report
improvements. The HTML preview uses fabricated data. Formatting an existing
report, inspecting a configuration and preparing a source payload make no model
calls and start no simulator.

## What each command costs

| Activity | Coding-agent tokens | Judge tokens | Native / cloud compute |
|---|---|---|---|
| `expo-eval-report`, `expo-eval-suite check`, Harbor `--print-config` | None | None | None |
| `expo-mobile-eval prepare`, `expo-eas-eval prepare` | None | None | File preparation only |
| `expo-mobile-calibrate` | None | None | Builds and simulator trials |
| `expo-mobile-eval run` on an existing candidate | None | None | One build and simulator trial |
| `jobs/native/repairs.yaml` | Yes | None | One native verification per candidate |
| `jobs/codegen/models.yaml` | Yes | Yes, unless a deterministic guard applies | No native builds |
| `expo-eas-eval run` | None in the current worker | None in the current worker | Paid EAS workflow compute |

An attempt is an agent session, not a single API call. It can contain many model
turns. The full native job is 3 tasks × 1 model × 3 attempts = **9 coding-agent
attempts and 9 native verifications**. The current source-model ladder is
18 tasks × 5 configurations × 3 attempts = **270 coding-agent attempts**, plus
judging. Do not use that ladder as the first smoke test.

Native calibration at the default three repetitions does 6 modal trials,
9 slider trials and 12 picker trials if all three tasks are requested separately.
That is 27 native builds/trials and zero LLM calls. Start with one repetition of
one task. Build timings, token totals and prices have not been measured for the
new native checks; no dollar estimate is implied by the illustrative report.

## 1. Inspect a one-attempt plan without running it

From the repository root, after `uv sync --dev`:

```sh
uv run expo-eval-suite check

uv run harbor run -c jobs/native/repairs.yaml \
  --path tasks/codegen \
  --include-task-name sdk-04-image-picker-canceled-assets-guard \
  --n-attempts 1 --job-name native-picker-pilot --print-config
```

This exact plan was inspected with `--print-config`: it resolves to the single
picker task, one `sonnet@low` host-agent attempt and the native verifier. The
flag exits after configuration output. It does not run the agent or verifier.

## 2. Prove the native checker works before spending agent tokens

This step runs native apps. It needs the Mac/Xcode/iOS runtime, Node, CocoaPods
and pinned device-driver prerequisites from
[the native guide](evaluation-quality.md). It needs no model login or Expo token
when run locally.

```sh
uv run expo-mobile-calibrate \
  --task sdk-04-image-picker-canceled-assets-guard \
  --attempts 1 --output runs/native-picker-calibration
```

Expected calibration behavior:

| Control | Expected application outcome | Why |
|---|---|---|
| Unchanged baseline | Builds, fails a UI assertion | The library button is not implemented |
| Reference | Passes every native check | Cancel is safe and successful selection renders |
| Alternative reference | Also passes | The checker must accept more than one correct implementation |
| Distractor | Builds, fails successful selection | The code validates the result but discards the selected URI |

The **calibration** passes only when all four expected outcomes hold. A red
application failure is expected for a negative control. A missing tool, failed
reference, or unbuildable negative control is a failed calibration, not evidence
of a weak model. The current picker selectors and all native profiles still need
this validation. Do not assume the first calibration will be green.

Repeat successful calibration on the intended runtime before publishing model
comparisons. If a control fails unexpectedly, fix the fixture/check first and
rerun that calibration; do not start the full model ladder.

## 3. Evaluate one generated candidate, then expand deliberately

After calibration, the following launches the one-attempt model pilot. It is
the inspected command with `--print-config` removed:

```sh
uv run harbor run -c jobs/native/repairs.yaml \
  --path tasks/codegen \
  --include-task-name sdk-04-image-picker-canceled-assets-guard \
  --n-attempts 1 --job-name native-picker-pilot --yes
```

The host coding agent edits a copy of the baseline. The native verifier then
builds those submitted files, installs the result on a disposable simulator,
drives cancellation and successful selection, saves evidence, and cleans up.

The first useful outcome is proof that the whole loop is healthy. One trial is
not a reliable model comparison. Once the loop works, compare two configurations
on the same three tasks and runtime, with three repetitions each: 18 coding
attempts. Inspect the disagreements before expanding the task set.

An existing completed candidate can skip the coding agent:

```sh
uv run expo-mobile-eval run \
  --task sdk-04-image-picker-canceled-assets-guard \
  --candidate /absolute/path/to/completed-app \
  --output runs/existing-picker
```

For cloud compute, prepare that same candidate with `expo-eas-eval prepare
--task ... --candidate ... --output .context/eas-picker`, then use
`expo-eas-eval run --project .context/eas-picker --output runs/eas-picker`.
The controller reads `EXPO_TOKEN` and `EAS_EVAL_PROJECT_ID` from `.env.local`.
The worker verifies the completed candidate; it does not start a cloud coding
agent. The cloud path uses an EAS workflow-owned simulator, without Sandbox MCP.
Full [cloud setup and recovery commands](running-mobile-evals.md) are separate.

## 4. Read results without consuming more model tokens

```sh
# Harbor model pilot:
uv run expo-eval-report runs/native-picker-pilot -o outputs/picker-report.html

# Scripted native calibration, or a standalone candidate:
uv run expo-eval-report runs/native-picker-calibration -o outputs/calibration-report.html
uv run expo-eval-report runs/existing-picker -o outputs/existing-picker-report.html

# Downloaded native EAS evidence:
uv run expo-eval-report runs/eas-picker -o outputs/eas-picker-report.html

# Local viewer for recorded Harbor runs:
uv run expo-eval-viewer
```

Reports only read files. They neither replay the simulator nor ask an LLM to
explain a failure. The default viewer address is `http://127.0.0.1:4477`.
Static HTML works offline; recorded screenshots are embedded, with up to three
per attempt. The native directories retain the complete evidence alongside it.

Read the report in this order:

1. **Measurement and calibration.** Native behavior, source review and simulator
   operation are different questions. The report does not infer calibration
   from high scores or merge them into a single mobile-app score.
2. **Coverage and errors.** Check recorded versus planned outcomes, pending work
   and missing results. A lost simulator connection is an execution error; it is
   not a successful or ordinary failing app test.
3. **Task matrix.** Compare full passes and each attempt, not just an average.
   Two passes and one failure suggest inconsistency worth investigating.
4. **Checks and evidence.** Click an attempt to see its named checks, source
   reasoning where present, screenshots, available log excerpts and provenance.
5. **Cost.** Recorded agent spend is incomplete if some attempts lack usage.
   Judge spend and EAS compute are excluded, not silently estimated as zero.

Completion is fully passing attempts divided by recorded outcomes, including
execution errors. Pending/unstarted/missing outcomes are displayed separately.
Mean score uses valid results and averages tasks equally; it is secondary to
completion for native behavior. Three repetitions can reveal flakes, but they
do not establish a precise ranking or a general probability of success.

## Do the tasks and static judging make sense?

Yes, as a focused regression suite. There are **28 task definitions**, not 28
fully runnable Expo apps: 21 coding tasks and 7 fixed-app simulator tasks.
The external result-import task has been removed. The three native repair profiles are a subset of the 21
source tasks, not three additional task definitions.

Static judging is useful for explicit API usage, lifecycle cleanup, routing
contracts and checking that code connects an event to its intended result. It
cannot establish that UIKit stays responsive, a thumb physically moves, an app
builds, a keyboard leaves buttons reachable, or content survives a relaunch.
Use native behavior as the primary outcome where supported, with the source
rubric as a separate diagnostic. Do not average the two into one score.

Some rubrics intentionally require a particular API: those are API-knowledge
tests. Product repair tasks should accept alternate valid designs unless the
prompt names a concrete constraint. Calibration needs plausible wrong fixes and
multiple correct implementations to catch overly narrow judging. Eight imported
tasks still lack dedicated realistic distractors.

The next additions should cover **navigation/deep links, persistence across
relaunch, Android keyboard/back behavior, and a data-dependent user journey**.
Keep each addition tied to a reproducible bug, a correct reference and a
behavioral failure check. The current seven SwiftUI probes remain useful for
comparing device tools; they should not be reported as Expo code-generation
quality. The current four-step flow checks order across screens, not yet a
journey where later inputs depend on earlier outputs.

## Report changes

| Before | After |
|---|---|
| One source-judging page for every kind of run | Separate native, source, device-use, smoke and unversioned views |
| Large bar charts and averages dominated | Completion-first summaries, outcome bars and a compact task matrix |
| Individual repeats hidden behind means | Accessible, clickable attempt symbols with pass, partial, fail, error and pending states |
| Missing records could resemble successful cells | Explicit planned coverage, missing counts and neutral incomplete cells |
| Native evidence absent from the static report | Named checks, source reasoning, embedded screenshots and bounded log excerpts |
| One global judge label | Per-attempt judge, experiment, backend, suite, cost and token metadata |
| Long pages with no task filtering | Search filters matrix rows and attempt details; measurement controls work independently |
| Native standalone and EAS records required manual inspection | The same reader accepts Harbor, native calibration, standalone candidates and downloaded native EAS evidence |
| Negative controls resembled model failures | Calibration records retain control names and explain their expected application failures |
| Readability depended on wide charts | Responsive tables, readable hierarchy, light/dark colors, keyboard focus and adequate hit areas |
| A UI change altered the evaluator fingerprint | Presentation files are excluded from the scoring/execution suite identity |
| Run costs and the first experiment were scattered across guides | A verified configuration-only command, one-attempt pilot and explicit token/compute boundaries |

The illustrative preview is generated by the production report renderer. Its
scores, model labels and dollar amounts are fabricated design fixtures, not
observed performance, predictions or price estimates.

Validation before the folder cleanup: 87 Python unit tests passed; suite definitions
match the lock; `git diff --check` passed. The desktop browser preview was
checked for separate measurement views, task filtering and clickable failure
details. No model evaluation, native build, simulator calibration or EAS job
was run. Native behavior and cloud execution remain unverified for this revision.
