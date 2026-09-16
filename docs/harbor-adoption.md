# Harbor regrading and executable paywall checks

Implemented and exercised on 16 September 2026. The paywall's normal grader now
executes its policy contract before source review. Both retained Sonnet answers
that previously received full source credit fail this contract. Harbor can now
save coding submissions and regrade them without generating another answer.

## Dependencies and scope

Harbor is pinned to **0.23.0**. Rewardkit is pinned to the reviewed upstream
commit **`cfc54c995e90cd438deb862189a58053b9d89fd3`**, whose package version is
0.2.1. This is an explicit Git dependency: the stricter validator was not yet in
the published 0.2.0 release when checked. `uv.lock`, the shared verifier and all
19 task copies use the same revision. Unknown criterion types and malformed
judge configuration fail before any provider call. Upstream judge errors,
including errors nested inside grouped details, cannot publish a candidate score.

The pre-merge upstream check found Harbor 0.23.0 is still the latest stable
release (nightly prereleases also exist). Rewardkit remains unpublished at
0.2.1; its package files at the pin match upstream main at
`22185e9c2b8cf9ba966c2dcd1155cd5dce54937f`, so no further dependency change was
needed. See [Harbor releases](https://pypi.org/project/harbor/) and
[Rewardkit releases](https://pypi.org/project/harbor-rewardkit/).

The reviewed [Harbor revision](https://github.com/harbor-framework/harbor/tree/cfc54c995e90cd438deb862189a58053b9d89fd3)
and [regrade documentation](https://docs.harborframework.com/core-concepts/jobs/regrade)
explain the upstream components. Our implementation targets the published
Harbor 0.23.0 behavior: separate verifiers build from `tests/` and skip a later
test upload. Every coding task therefore includes `tests/Dockerfile`. The local
Mac adapter materializes the same directory into a separate verifier workspace.
Candidate deletions remain deleted; starting verification cannot erase the
agent workspace or restore the broken baseline.

The Callstack checkout was already at our imported revision,
[`f7a46a71`](https://github.com/callstackincubator/evals/tree/f7a46a71da58eece312e37a1f5291e9fd0cc236b).
This change does not import additional tasks or replace the host Claude adapter.

## What a paywall score means

| Mode | Headline reward | Model calls |
|---|---|---|
| `judge` (normal grading) | Every policy criterion and the screen-integration criterion must pass | Source judge only after policy passes |
| `behavior` | All 4,860 policy cases pass | None |
| `reference` | Exact match to the supplied reference | None; plumbing smoke check only |

The policy contract enumerates identity, readiness, entitlement and placement
combinations. It returns named failed groups, failure counts and representative
counterexamples. Valid alternative implementations pass. The helper must be a
standalone CommonJS function as stated in the task instructions.

The contract evaluates submitted JavaScript in a restricted Node context with
per-call deadlines. Node receives no model credentials or `NODE_OPTIONS`, and
its permission flags limit filesystem reads. Invalid or nonterminating helpers
fail the task; a missing Node executable or a broken contract process is an
execution error. This is not a general-purpose sandbox for arbitrary applications.

A failing policy immediately produces a zero combined score and records
`source_review_skipped`. A passing policy proceeds to source review, whose
original score remains in `source_review`; executable results replace the three
policy criteria, and the remaining screen criterion must also pass. The final
gate checks that every numeric criterion equals **1**. Rewardkit's `all_pass`
aggregator tests positivity, so applying it to partial scores would be too weak.

`reward-details.json` preserves the effective criteria. `behavior-details.json`
contains contract evidence and the helper hash; `submission-manifest.json`
contains the reviewed source hashes. Reports keep source review, combined
source/policy, policy-only, native UI and device-use measurements separate.
These policy checks do not build the app, execute purchases or validate native UI.

## Run the free controls

Use Python 3.13 and Node 24 or newer. The verified host used Node 26.4.0; the
Docker scaffolding provides Node 24. Docker builds were not exercised in this
validation.

```sh
export UV_PYTHON=3.13
uv sync --dev --python 3.13 --locked
uv run expo-eval-suite check
uv run pytest -q

uv run expo-codegen-calibrate --behavior-only \
  --only feedback-11-anonymous-paywall-eligibility \
  --jobs 1 --output runs/paywall-calibration.json

uv run harbor run -c jobs/codegen/behavior-controls.yaml \
  --job-name paywall-policy-controls --yes
```

Calibration expects empty=0, unchanged baseline=0, commented baseline=0,
reference=1, alternative reference=1 and distractor=0. The Harbor job expects
no-op=0 and oracle=1, with no execution errors. These commands require no model
login and start no simulator. Policy-only calibration does not establish that
the current source judge accepts both references or detects disconnected UI.
Full current judge calibration remains required before including paywall in the
frozen model-comparison cohort; that cohort remains at 18 tasks.

## Regrade saved submissions

All 19 coding tasks now declare `/app` as an artifact. Dependency directories,
Git metadata, common credential files and image scaffolding are excluded.
The artifact includes unchanged supporting source as well as edits. Reviewable
symlinks are rejected by the local capture/verifier path. Ordinary source may
still contain hard-coded secrets; artifact exclusions are not a secret scanner.

```sh
uv run expo-codegen-regrade runs/paywall-policy-controls/TRIAL_DIRECTORY \
  --task tasks/codegen/feedback-11-anonymous-paywall-eligibility \
  --output runs/paywall-regrade --mode behavior

uv run expo-eval-report runs/paywall-regrade -o outputs/paywall-regrade.html
```

Replace `TRIAL_DIRECTORY` with a completed trial, and use a new output directory.
The command invokes Harbor's actual `trial regrade` implementation. Default mode
is `behavior`; `--mode judge --judge claude-code --model sonnet` opts into source
judging when the policy passes and may consume subscription usage. Regrading
skips the coding agent, not necessarily verifier costs. The report recognizes
Harbor's `source_trial` record and does not count retained original agent usage
as new spending or pool regrades with fresh attempts.

The September pilot predates explicit source artifacts. Its retained workspaces
can be recovered only with the original tracked audit:

```sh
uv run expo-codegen-regrade \
  runs/sonnet-effort-discovery/feedback-11-anonymous-paywall-el__AVfukbp \
  --task tasks/codegen/feedback-11-anonymous-paywall-eligibility \
  --output runs/paywall-legacy-regrade \
  --legacy-audit results/sonnet-effort-2026-09-16.json --mode behavior
```

Recovery compares the complete normalized source manifest with the original
audit hashes. It creates a separate `.sources/` copy with an explicit artifact
manifest and `recovery.json` provenance. A changed candidate is rejected; original
trial files and original scores remain untouched. These old workspaces are local
run evidence, so a fresh checkout cannot reproduce this particular replay from
the small tracked summary alone.

## Observed results

| Retained Sonnet 4.6 answer | Original source score | New combined score | Failed policy cases |
|---|---:|---:|---:|
| Low effort | 1 | 0 | 8 / 4,860 |
| High effort | 1 | 0 | 4 / 4,860 |

Both accept an empty anonymous-ID suffix; the low-effort answer additionally
accepts matching empty identities. Both therefore fail the required identity
criterion. Case counts are diagnostics over correlated states, not independent
trials or partial-credit rewards. This pair does not demonstrate a reliable
benefit from increased thinking.

All 108 offline tests and all 38 empty/baseline guards passed. Six policy
calibration controls, two actual Harbor control trials, both saved
Sonnet regrades, and regrading a newly captured oracle artifact produced their
expected outcomes. Early integration attempts exposed test-directory and local
workspace bugs; those were fixed and successful runs retained separately. The
machine-readable [adoption results](../results/harbor-adoption-2026-09-16.json)
record run locations, hashes and validation scope.

The pre-merge review passed 131 tests and repeated the six policy controls and
a Harbor Sonnet replay. It also bounded inspection of the exported helper,
fixed regrade usage in the live viewer, and tightened the OAuth tasks' evidence
binding and consent-denial calibration. These review results are appended to
the audit; the original trial records and scores remain unchanged.

No new coding-model or judge calls were made for this validation. The older
pilot still has an unpriced timed-out call, and its existing budget guard blocks
fresh paid dispatch until that is reconciled. No new native, simulator or EAS
evaluation was run. Broader effort comparisons and additional Callstack state
tasks remain follow-up work after grading calibration and budget reconciliation.
