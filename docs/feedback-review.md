# Feedback review — 14 September 2026

The live Expo CLI Feedback MCP contained **368 conversations and 376 messages**.
We read all **16 `evals` conversations and the one legacy `eval-candidate`** in
full, including metadata. A text search for `Task:` returned the same 17. Two
reports arrived after the September 10 review; the other 15 texts are unchanged.
This covers the two eval categories, not every report in the service.

| Category | Conversations |
|---|---:|
| skills | 164 |
| unknown | 109 |
| docs | 39 |
| eas-cli | 17 |
| evals | 16 |
| expo-cli | 10 |
| mcp | 6 |
| simulator | 5 |
| eval-candidate | 1 |
| expo-updates | 1 |

## Decisions

| Outcome | Count | Findings |
|---|---:|---|
| Already covered | 7 | Sticky shop grid, modal handoff, relative slider, sortable layers, Android modal keyboard, invite web fallback, Three scene cleanup |
| Task authored | 3 | Anonymous paywall eligibility (`feedback-11`), native fixed amount column (`feedback-12`), authentication field render path (`feedback-13`) |
| Suitable, still planned | 1 | Calendar subrequest budgeting (`feedback-07`) |
| Needs evidence | 4 | Water-ripple transition, initial large-title visibility, Skia card fidelity, notification service extension bundle metadata |
| Outside the current task families | 2 | Physical-device tunnel instability and local-build disk/toolchain failures |

The human reasoning is in [TRIAGE.md](../tasks/TRIAGE.md). The
[structured inventory](../tasks/feedback-reviews.json) records D1 UUIDs, CLI IDs,
text checksums, task IDs and accepted service review revisions. All 17 decisions
were saved through `feedback_review_eval` and returned by the service's current
review filter. The legacy Linear link was preserved. No classifier or issue
routing was changed. “Added” means authored, not calibrated.

## New since September 10

### Native amount column (`feedback-12`)

[Task prompt](../tasks/codegen/feedback-12-native-fixed-amount-column/instruction.md).
The report describes a fixed column displaced on Android at 360dp while web
validation passed. The original app was not supplied. Our reconstructed fixture
uses shared positive `flex`, an explicit width, and longhand overrides. With
native Yoga defaults the amount region collapses to zero; with Yoga's
`useWebDefaults` the amount region remains 112dp. This is a related reproducible
constraint failure, not a claim to recreate the exact reported off-screen image.

Two valid repairs pass four widths (320/360/390/430dp), two descriptions, and
actual React visibility-toggle callbacks. A plausible repair that only makes
the description shrink leaves the amount conflict broken. The check runs Yoga
3.2.1 with stipulated text metrics. It is neither a browser rendering test nor
an Android font/layout screenshot. RN 0.86.3's bundled Yoga `Node.cpp` was also
read to confirm its flex-basis and shrink resolution. See the
[Yoga styling defaults](https://www.yogalayout.dev/docs/styling/) and
[React Native flex documentation](https://reactnative.dev/docs/flexbox/).

### Authentication render path (`feedback-13`)

[Task prompt](../tasks/codegen/feedback-13-auth-field-render-path/instruction.md).
The report describes three edits to a reusable field that never affected the
separate SwiftUI authentication form. The reconstructed app has sign-in,
create-account and Settings routes. Auth fields must match a 52-point button;
Settings intentionally keeps its 44-point field.

The tests render the actual React component tree, record the native control
boundary, follow input/submit callbacks, and inspect ordered frame/padding
modifiers. Both correct designs pass. A wrong fix to the similarly named Settings
component leaves authentication broken and changes unrelated behavior.
`@expo/ui` 57.0.18 declarations confirm the supplied Host, input and modifier APIs.
See [Expo UI TextField](https://docs.expo.dev/versions/latest/sdk/ui/swift-ui/textfield/)
and [SwiftUI modifier composition](https://developer.apple.com/documentation/swiftui/configuring-views).
The modifier probe is a bounded authoring contract, not SwiftUI geometry, Dynamic
Type, keyboard or native interaction validation.

### Running the inexpensive checks

```sh
uv sync --dev
npm ci --prefix tests/contracts
uv run pytest tests/test_native_contracts.py -q
# Inspect one authored control as JSON:
node tests/contracts/run-controls.mjs layout reference
node tests/contracts/run-controls.mjs auth distractor
```

The eight new control tests exercise the baseline, reference, alternative and
wrong fix for both tasks. The JS runner only accepts these repository-owned
controls; it is not a sandbox for untrusted model submissions. Package versions
are pinned in `tests/contracts/package-lock.json`.

The subsequent [single-attempt source pilot](new-feedback-pilot.md) found a
calibration failure in each task. Both now declare `source-calibration-failed`,
have no native runtime profile, and remain outside the frozen 18-task comparison
jobs. The pilot retains raw grades and source-inspection notes separately.
Native geometry still needs a separate authorized runtime run.

## Paywall task added September 10

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
cohort. The repository now has 21 coding definitions and seven simulator tasks.
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
and deployed on 10 September 2026. All 17 review decisions were saved on
September 14 after rereading complete evidence and using current revisions.
The current service search returns all 17 as reviewed. Future new/edited messages
will make reviews stale. A checksum aids comparison; it does not replace reading
new evidence. Do not infer review state from the classifier's `non_actionable`
status. No Feedback Worker code or deployment was needed for this review.

The feedback inventory review itself ran no model evaluation, native build,
simulator, EAS job, semantic embedding, feedback reprocessing or Linear mutation.
The separately authorized PR pilot is documented in the guide linked above.
