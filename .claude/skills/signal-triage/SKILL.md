---
name: signal-triage
description: Decide whether an Expo CLI/skills feedback signal becomes a tasks/codegen/feedback-* eval, an upstream product fix, or both. Use BEFORE authoring any eval from a field report — when reading new submit-expo-feedback signals, eval-candidate submissions, or bug reports about models failing on Expo work.
---

# Signal triage: eval, upstream fix, or both

A feedback signal only becomes an eval when it measures a **durable model
capability**. Most signals are instead (or additionally) product feedback that
belongs upstream. Run every signal through this procedure before writing any
task files; record the verdict as a row in `tasks/TRIAGE.md` before starting
authoring.

## Gate 0 — dedupe

Grep the signal's feedback id against existing tasks first:

    grep -rl "<feedback_id>" tasks/

One report can hold several findings (bca74ecdb803 produced feedback-01 AND
feedback-02) — dedupe per *finding*, not per report. Anything already covered
needs no new task.

A hit may land in `tasks/TRIAGE.md` rather than a task dir — that is the
verdict ledger, and it means the id was already triaged (possibly dropped or
held). Read its row instead of re-deriving the verdict; dropped and held ids
exist ONLY there.

## The three questions

**Q1 — Who failed: the model, or the product?**

- A model chose a wrong approach while a correct one was available with the
  tools at hand → eval material.
- Expo-owned code (eas-cli, an SDK package, skill text) misbehaved and the
  agent merely *discovered* it → product material. A polished root-cause
  report means the agent **succeeded**; that is not a failure signal at all.
- Both (misleading skill text that models follow into a real bug) → both
  tracks: fix the guidance upstream AND build the eval as its regression
  harness.

**Q2 — Who owns the root cause? (decides durability)**

- Apple/UIKit/Yoga/React Native platform behavior: durable. Expo cannot fix
  it, models must handle it forever, the eval stays valid.
- Expo-owned bug: transient. Expo will ship a fix, and the eval's ground
  truth — including its distractor — can invert with one release. Do not
  build an eval whose correct answer depends on an upstream bug staying
  unfixed. (Sharp test: "would the distractor become the *right* answer
  after the fix ships?" If yes, no eval.)
- Pinning versions does not rescue transient signals: pinned SDK tasks stay
  representative of code models must still write; an archived tool bug is
  representative of nothing once fixed.

**Q3 — Is it on-mission for a family?**

- expo-codegen / expo-feedback: writes correct Expo app code, especially
  where popular guidance misleads. The best tasks are traps (CONTRIBUTING.md,
  "Field-sourced tasks").
- simbench: drives a real app on the simulator with programmatic state
  verification. A codegen signal with runtime-visible symptoms can graduate
  to a simbench behavioral variant later; note that in the verdict.
- Debugging Expo's own toolchain is currently no family's mission — routing
  upstream is not a loss.

## Verify before authoring

- The reporter is often the failing (or auto-submitting) agent itself.
  Self-diagnoses are unproven: reproduce every code-level claim against the
  pinned source before it becomes rubric ground truth (e.g. fetch the exact
  npm tarball and read the shipped code; for platform behavior, check the
  report tested it on real devices/OS versions).
- If the report contains no verified correct fix, the reference solution is
  yours to reconstruct — budget for self-verification and say so in the
  task's motivation.
- Check `latest` as well as the pinned version: a trap still shipping in the
  current release (slider falsy-zero, present in 5.0.1 AND 5.2.0) hardens
  durability and usually warrants a parallel upstream issue.
- Maintainer intent is durability evidence: an explicit wontfix or a
  merged-then-reverted fix on the platform tracker (RN modal overlap,
  facebook/react-native#50399) is the strongest possible Q2 answer.
- A report marked "resolution pending" blocks authoring only while the
  mechanism is unverifiable. If public platform docs pin the accounting and
  arithmetic (EAS Hosting subrequest budget), ground truth can be built
  without the reporter's fix — but parameterize every number the platform
  can change (the paid subrequest limit went 1,000→10,000 on 2026-02-11).

## Verdicts and required artifacts

| Verdict | When | Artifacts |
| --- | --- | --- |
| Eval (feedback-NN) | Model failed, durable root cause, on-mission | Task per CONTRIBUTING.md: `metadata.motivation` + `feedback_id`, environment reproducing the trap, constraints that block deleting the triggering feature, `solution/distractor/` = the fix the field tested and found insufficient, full calibration bracket (empty=0, baseline=0, reference=1.0, distractor<1.0) |
| Upstream fix | Product failed (Q1) or transient root cause (Q2) | Issue/PR against the owning repo with the verified causal chain; workaround into skill text if users need it now |
| Skill edit + eval | Guidance misled AND the underlying behavior is platform-owned | Both artifact sets; the eval tests handling the *behavior*, never "recite that the old rule was wrong" |
| Drop | Not reproducible, already covered, or no capability signal | One-line note with the feedback id and reason |

## Worked examples (2026-08-06 batch)

- **bca74ecdb803** (headerTransparent + automatic content inset): skill text
  misled, but the cold-launch inset behavior is Apple-owned → skill edit +
  evals feedback-01/02. Valid because the rubric tests the explicit-inset
  fix, not knowledge of the rule's wrongness.
- **4111d2c27a14** (eas-cli capability sync disables iCloud for
  kvstore-only apps): Expo-owned CLI bug, agent succeeded in diagnosing it,
  and the portal-re-enable distractor becomes correct once the one-line
  mapping fix ships → upstream issue/PR only, no eval.
- **911b52e0e368** (percentage-height grid + sticky chrome coupled to a
  native Animated.Value across freezeOnBlur): model failed twice
  (GPT-5.6, physical-device repro), root causes are Yoga/native-driver
  mechanics → eval feedback-03. Report shipped no verified fix, so the
  reference was reconstructed and the rubric judges properties (intrinsic
  heights, visibility derived from offset, no imperative native resets),
  not one library choice.

## Worked examples (2026-08-12 batch)

- **029b2a2da3d2** (overlapping Modals freeze touch, SDK 56): verified in RN
  0.85.3 source — `_isPresented` flips before presenting with no failure
  check, and the iOS `isRendered` latch keeps an invisible screen-sized,
  touch-claiming host view mounted; the frozen state is absorbing and the
  sibling-overlap repro is fully deterministic. Identical code in RN 0.87,
  Meta explicitly declined to fix (#50399) → eval feedback-04. Rubric judges
  properties (single visibility source of truth, completion-signal
  sequencing, post-flow tap oracle); the editor-nested-inside-the-open-modal
  pattern is legit and must pass. Strong later simbench variant. Authored as
  feedback-04-modal-editor-touch-freeze; calibrated empty=0, baseline=0,
  reference=1.0, distractor=0.0 on two stable judged runs.
- **3892d1c10f3c** (slider recenter, 5.0.1): three verified layers — the JS
  wrapper coerces falsy 0→undefined (in 5.0.1 AND latest 5.2.0), the Fabric
  codegen default is 0 so the native `oldProps.value != newProps.value`
  guard never fires, and no `prepareForRecycle` means remounts can recycle
  stale thumbs → eval feedback-05 (pin 5.0.1) + upstream issue to
  react-native-slider. The reference must force a real prop transition
  (remount keyed per release + a non-default positive midpoint); a constant
  midpoint prop alone never re-sends to native. Authored as
  feedback-05-slider-relative-recenter with the real 5.0.1 wrapper vendored
  into environment/node_modules/ so the read-the-installed-source capability
  is exercisable; calibrated empty=0, baseline=0, reference=1.0,
  distractor=0.5 on two stable judged runs.
- **1610fc625460** (sortable grid): glitch is inherent — layout transitions
  are commit-triggered snapshots and cannot track a continuous gesture;
  every credible implementation (react-native-sortables,
  draggable-flatlist, Candillon) keeps layers stable, drives motion from
  shared values, and commits order once on drop → eval feedback-06. Rubric
  bans mid-gesture commit-driven sibling motion and multiple order commits —
  NOT LinearTransition per se (post-drop settle and add/remove transitions
  are legitimate). Authored as feedback-06-sortable-grid-stable-layers;
  calibrated empty=0, baseline=0, reference=1.0, distractor=0.25 on two
  stable judged runs.
- **019ff4bd-822c…** (EAS Hosting subrequest budget): upgraded HOLD → eval
  feedback-07. Cloudflare docs pin the accounting the model ignored (every
  fetch, every redirect hop, `connect()` per connection, the 6-connection
  concurrency gate) and Google Calendar docs pin the arithmetic (2,500
  maxResults/page, 1,000 calls per batch = 1 subrequest, `nextSyncToken`) —
  an offline fetch-counting mock with a stipulated budget B separates
  batched from naive syncs by >1000x. The reporter's pending resolution is
  not load-bearing.
