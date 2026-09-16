# Feedback review — 10 September 2026

The live Expo CLI Feedback MCP contained 350 conversations and 357 messages.
We read all **14 `evals` conversations and the one legacy `eval-candidate`** in
full. A text search for `Task:` returned the same 15. This is an exhaustive
review of those two categories at that time, not a review of all 350 reports;
other categories may contain additional uncategorized candidates.

| Category | Conversations |
|---|---:|
| skills | 152 |
| unknown | 107 |
| docs | 38 |
| eas-cli | 16 |
| evals | 14 |
| expo-cli | 10 |
| mcp | 6 |
| simulator | 5 |
| eval-candidate | 1 |
| expo-updates | 1 |

## Decisions

| Outcome | Count | Findings |
|---|---:|---|
| Already covered | 7 | Sticky shop grid, modal handoff, relative slider, sortable layers, Android modal keyboard, invite web fallback, Three scene cleanup |
| Added locally | 1 | Anonymous paywall eligibility (`feedback-11`) |
| Suitable, still planned | 1 | Calendar subrequest budgeting (`feedback-07`) |
| Needs evidence | 4 | Water-ripple transition, initial large-title visibility, Skia card fidelity, notification service extension bundle metadata |
| Outside the current task families | 2 | Physical-device tunnel instability and local-build disk/toolchain failures |

Five newer reports were absent from the old triage ledger. One became a task;
four need more evidence. The previously missing record IDs for the Three,
tunnel and local-build reports are now backfilled. No existing task was
duplicated. Existing calibration notes are historical evidence, not fresh runs.

The human reasoning is in [TRIAGE.md](../tasks/TRIAGE.md). The corresponding
[structured review inventory](../tasks/feedback-reviews.json) holds the stable
D1 record UUID, CLI feedback ID, a text checksum and decisions with task IDs.
It explicitly records that the decisions have **not been applied to the live
feedback service**. No extra top-level folder or vendored feedback checkout is
needed.

## The new task

[`feedback-11-anonymous-paywall-eligibility`](../tasks/codegen/feedback-11-anonymous-paywall-eligibility/instruction.md)
tests application state reasoning. The original report describes a pre-render
identity guard blocking a placement paywall for valid anonymous sessions;
repeated OTA changes did not fix that gate. The original app source was not
provided, so this is an explicitly reconstructed fixture, not an exact replay.

RevenueCat documents anonymous customer identities and the creation of a new
anonymous identity on logout. This supports the premise that an account login
is not universally necessary for purchases. Whether to show a particular
placement is an app policy, which the task states explicitly. See
[RevenueCat: Identifying Customers](https://www.revenuecat.com/docs/customers/identifying-customers).

The fixture keeps the complete screen-to-helper path. The repair must allow
eligible anonymous users while preserving resource readiness, identity
synchronization, premium entitlement and placement guards. Local auth/customer/
offering snapshots replace external services. It needs no RevenueCat token,
purchase, backend or OTA update.

Two independently implemented references pass 4,860 offline state combinations
each. The starting code fails anonymous eligibility. A reconstructed plausible
wrong fix that removes the guards fails the intended identity, loading,
entitlement and placement checks. These checks verify authored control logic;
they are **not the scoring judge**, a candidate-model run or native validation.
The task remains `requires-judge-calibration`. Its four source criteria also
check that the helper remains connected to the screen.

Existing comparison jobs deliberately retain their frozen 18-task source
cohort. The repository now has 19 coding definitions and ten simulator tasks.
The new task can be inspected without executing it:

```sh
uv run harbor run -c jobs/codegen/models.yaml \
  --path tasks/codegen \
  --include-task-name feedback-11-anonymous-paywall-eligibility \
  --n-attempts 1 --job-name paywall-candidate --print-config
```

That models config still contains multiple agent configurations. Before a paid
pilot, choose one configuration, inspect the complete resolved plan, calibrate
the judge's controls and only then remove `--print-config`. Do not add this task
to the comparison cohort until calibration establishes useful discrimination.

## What would make the held reports reliable?

- **Ripple transition:** original HTML reference, recorded expected motion and
  candidate motion, plus a frame alignment/comparison contract. “Looks like a
  water ripple” alone is not a repeatable oracle.
- **Large title:** a minimal reproducible app and version-specific causal
  investigation. It differs from the inset task, but the reported workaround
  could depend on a transient Router implementation.
- **Skia card:** source reference images, fixed comparison dimensions and a
  separate motion fixture. A reference image was mentioned but not attached.
- **Notification extension:** exact generated bundle and missing Info.plist
  fields, with the responsible CNG plugin. The future check can inspect a
  generated bundle contract without repeatedly paying for EAS/TestFlight builds.
- **Calendar candidate:** specify the mocked API and batch response behavior,
  parameterize the subrequest budget, and test real fan-out, partial failures
  and retries. Do not encode a changing provider-plan quota as permanent truth.

## Recording decisions in the feedback service

The MCP now has a dedicated eval-review tool. Its `non_actionable` status
remains part of routing feedback away from Linear; it does not mean “seen by
the eval maintainer.” The legacy candidate also has a Linear link that should
stay untouched by an evaluation review.

The feedback-worker changes add `feedback_review_eval`, a separate D1
review history and a dashboard filter/details view. A review contains one or
more finding decisions: `added`, `covered`, `candidate`, `needs_evidence`, or
`not_suitable`. Added/covered findings require task IDs. Reasons state evidence
gaps and calibration limitations; “added” never means “validated.”

The tool uses the current source revision and review revision from
`feedback_get`. New or edited messages make prior reviews stale. Concurrent
writes are rejected, and repeating the same completed save is idempotent.
Search can filter unreviewed/current/stale reviews and individual decisions;
details expose reasons and task references. The dashboard filter covers its
latest 200 loaded conversations, while MCP search paginates the whole database.

Those worker changes were merged in
[Feedback Worker PR #26](https://github.com/expo/cli-feedback-worker/pull/26)
and deployed on 10 September 2026. Migration `0017`, production health, tool
registration and review-state search were verified. The 15 decisions in this
repository have not yet been saved to the service. Before saving, reread each
conversation including messages and metadata, compare the intended decision
with the current evidence, then use freshly read revisions. A checksum is an
aid to comparison, not permission to skip reviewing new evidence. Do not infer
review state from the classifier or mark every `non_actionable` report reviewed.

No model evaluation, native build, simulator, EAS job, semantic embedding,
feedback reprocessing or Linear mutation was run for this review.
