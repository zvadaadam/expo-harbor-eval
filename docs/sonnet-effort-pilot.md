# Sonnet effort pilot and grading audit — 16 September 2026

This repository is useful for developing Expo repair evaluations. It does not
yet establish a reliable “low effort fails, high effort succeeds” benchmark.
The most consequential finding in this pilot is a real false positive: Sonnet's
source judge accepted paywall implementations that fail the task's existing
deterministic state contract.

## Experiment

The user authorized a $10 ceiling and Claude subscription authentication.
Candidates used `claude-sonnet-4-6` through Claude Code 2.1.273, at low or high
effort. The source judge used the same Sonnet model at fixed medium effort.
There was no change to task prompts or rubrics between conditions.

Three repair tasks were selected: slider recentering, sortable-grid motion,
and anonymous paywall eligibility. One attempt per task/effort formed discovery.
After the first grid pair, a repeat of **all three** pairs was specified, rather
than selecting only a favorable result. Each attempt used a fresh workspace.

The local host adapter used the macOS task sandbox plus CLI safe/restricted
mode. Candidate tools were Read, Write, Edit, Glob and Grep; the judge had only
read tools. Personal instructions, skills, hooks, memory, shell, web and MCP
were disabled. These results concern this constrained coding setup; they do
not measure an Expo skills bundle or an agent that can run its own tests.
The judge received source and the rubric, without candidate effort or its
transcript. Using the same model for generation and judging remains a source
of correlated errors.

All candidate, calibration and judge calls shared a serialized usage ledger.
Per-call limits were $0.75 for candidates and $0.20 for judges, with dispatch
stopping at $8.50 to leave headroom below $10. Reported amounts are CLI
API-equivalent usage under the subscription, not a subscription invoice.
Claude's small internal Haiku calls are included in that accounting.

The frozen suite SHA-256 was
`9b26c000ea9862a1d1026d97c876825d75749993e20f22a89c4c8e0c62e1076f`.
Python 3.13 was used: the pinned native LiteLLM dependency did not build on the
host's Python 3.14. Harbor was 0.18.0. The local protocol, configuration and
budget wrapper are retained in [`.context/sonnet-pilot`](../.context/sonnet-pilot/).

## Calibration and results

Before candidate runs, all 16 source-calibration brackets passed: six
deterministic empty/unchanged guards and ten judged controls across the three
tasks. Every reference passed all criteria; each negative control failed its
declared criterion. This was one calibration repetition, and the later
paywall counterexample shows that these controls were insufficient.

The first six attempts completed without execution errors:

| Task | Low effort source score | High effort source score | Independent evidence |
|---|---:|---:|---|
| Relative slider | 1.00 | 0.75 | High effort kept a constant value prop, so resetting state produces no changed value for native |
| Sortable grid | 1.00 | 0.50 | High effort reorders React-visible preview data during drag and uses a layout transition |
| Anonymous paywall | 1.00 | 1.00 | Both fail the existing 4,860-case helper contract |

The repeat was **incomplete**. The second low-effort grid submission scored
1.00. The high-effort grid attempt timed out after 540 seconds, without a CLI
usage receipt or a source edit. The cause of that timeout is unknown; it does
not establish a reasoning failure. The accounting wrapper then withheld the
remaining four attempts. There were seven scored candidates, one timed-out
candidate and four undispatched conditions out of twelve planned attempts.

Reported API-equivalent usage was **$2.2429**, including calibration and judging:
$1.0018 for completed candidate calls and $1.2411 for judges. The timeout has
an additional **unknown actual cost**; its $0.75 per-call allocation was reserved
in accounting, bringing the accounted amount to $2.9929. That reservation is
not a verified charge. No further model calls were dispatched after the
unknown receipt, and this report does not claim an exact total spend.

The complete first round had three full source passes at low effort and one
at high effort. Its source-score means were 1.00 and 0.75. These are descriptive
numbers from three tasks, **not** evidence that low effort is better. The
paywall behavioral failures invalidate treating those source passes as full
product correctness. The incomplete repeat cannot establish an effort effect.
No native UI passes are claimed.

The grid's completed high-effort attempt used 14,026 thinking tokens versus
1,217 for low effort, so the contrary result was not merely an unrecorded
effort setting. It still repeated the prohibited layout-based approach.
More thinking is a useful experimental variable, not a guaranteed improvement
on every task or every sample.

### Retained evidence

The tracked [machine-readable summary](../results/sonnet-effort-2026-09-16.json)
contains all twelve planned trial records, separate timeout/withheld outcomes,
source hashes, actual thinking-token counts, reported costs, the full
calibration summary and the offline grader probes. Raw candidate sources,
judge explanations and CLI envelopes remain in the local, gitignored
`runs/sonnet-effort-discovery/`, `runs/sonnet-effort-repeat/` and
`.context/sonnet-pilot/receipts/` directories.

The [HTML source report](../outputs/sonnet-effort-pilot.html) shows the original
source scores and execution errors. Its paywall scores must be read alongside
the behavioral countercheck below; the report does not ingest that extra
contract automatically. The audit JSON distinguishes four withheld calls from
the actual timeout, which Harbor's generic execution-error records do not.
The HTML report's costs cover candidate receipts only; use the audit JSON for
judge/calibration costs and the unknown-cost reservation.

### A concrete source-judge false positive

Both paywall candidates accept `appUserId: "$RCAnonymousID:"` with no suffix
when the session is logged out. With ready resources, no premium entitlement
and an assigned offering, they return the offering. The prompt requires null.
The low-effort candidate also accepts matching empty signed-in/customer IDs.

The rubric explicitly requires a nonempty anonymous suffix and a nonempty
signed-in ID, yet the judge marked the identity criterion as satisfied. It
reasoned from a nonempty whole string plus `startsWith`, which does not prove a
nonempty suffix. The pre-existing Node contract catches these failures.
The screen remains wired to the helper, so this is an application-policy
failure, not a disconnected-function concern.

Instrumenting the existing contract counted eight failing cases for low effort
and four for high effort. Per-case averages would exceed 99% while both still
violate an explicit requirement.

This is the strongest immediate grading improvement: execute the deterministic
contract on every paywall submission. Keep source review for screen wiring.
Require all behavioral groups to pass; a percentage over thousands of cases
would dilute a small but critical set of invalid identities. Add near-correct
negative controls with empty suffixes and empty signed-in IDs, since the
current “remove all guards” distractor is much easier for a judge to reject.

## Grading findings

| Priority | Finding | Evidence and recommended change |
|---|---|---|
| Fixed | Judge timeouts looked like legitimate zero scores | Rewardkit records zero-valued criteria with `error`. The runner now removes the candidate score and fails verification; calibration rejects those results; reports classify historical cases as errors. |
| Fixed | Four-decimal serialization broke calibration | A legitimate 5/6 score is emitted as 0.8333. Calibration now compares with the same serialization precision. |
| High | A source pass can hide a policy failure | The actual paywall candidates above fail deterministic checks despite full source scores. Execute their contract in grading. |
| High | Native negative-control calibration accepts unrelated failures | An offline probe with a successful build and an unrelated `native-ui` failure is accepted as a distractor. Require the intended named failed check and successful prerequisite checks. |
| High | Slider native checks omit interior offsets | An offline fake driver that always adds +/-0.50 for any nonzero drag passes all five current checks. A quarter-range nudge should add 0.125; that implementation adds 0.50. Add multiple interior drags, reversals and repeated releases. |
| High | Simulator-grid wrong-tap accounting can reset on relaunch | The Swift store starts `tappedColors` empty and overwrites `grid-taps.json` after a new tap. The journal retains previous events, but the verifier counts wrong taps only in the overwritten file. A five-wrong-tap journal followed by a red tap scores zero wrong taps. Count the complete event journal or persist/reload the history. |

There is also specification drift in the filesystem task: its prompt requires
a cache file, but the directory criterion accepts `Paths.document`; its fallback
criterion insists on a caught failed read, excluding a valid existence check
before reading existing content. Expo exposes a boolean `File.exists` property.
Judge the requested behavior and add an alternative reference using that API.
This is a rubric inspection finding, not a measured candidate result.
([SDK 56 FileSystem documentation](https://docs.expo.dev/versions/v56.0.0/sdk/filesystem/#exists-1))

The last three findings were reproduced against the actual verifier functions
using synthetic evidence. They demonstrate checker coverage gaps; no native
application was built or operated to produce those probes. Evidence is in
[`grading-probes.json`](../runs/sonnet-effort-pilot/grading-probes.json).

The two source-scoring fixes were applied before the pilot. The runner was
synchronized into all 19 coding tasks and the suite lock refreshed. All 85
repository tests passed. This audit did not alter task rubrics to make the
desired effort comparison appear.

## What would make this a strong Expo eval?

Keep source review, execution of submitted Expo apps, and fixed-app device use
as separate measurements. The seven SwiftUI simulator tasks measure device
operation; they do not establish Expo coding correctness. The 19 source tasks
provide useful screening, while only three currently have native scenarios.

Use **full completion of the product contract** as the headline result.
Partial criterion scores explain failure. Execution errors and budget-limited
attempts need separate counts, and the denominator must include the complete
planned cohort. A timeout must never become evidence that a task is hard.

Build a difficult set from realistic failures and near-correct repairs:
identity changes, stale state, canceled gestures, partial drag distances,
repeated navigation, and persistence across relaunch. State the product
requirements clearly while letting agents determine the implementation.
Multiple correct implementations should pass, and each wrong implementation
should fail for the intended reason.

Then repeat both effort settings on a fixed held-out cohort with identical
tools and budgets. Measure actual thinking tokens, cost, latency, completion
and judge agreement. Retain contrary results. A useful benchmark has room for
improvement; a low-fail/high-pass observation is evidence to replicate, not a
property to enforce by changing the grader after seeing submissions.

Native reference/baseline/distractor calibration remains unrun here. Until
that exists, source successes should be described as source successes.
