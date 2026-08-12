# Signal triage ledger

Verdict record for every triaged feedback signal — one row per *finding*, not
per report (procedure: `.claude/skills/signal-triage/SKILL.md`). This file
lives inside `tasks/` on purpose: Gate 0's `grep -rl "<feedback_id>" tasks/`
hits it, so already-triaged ids — including dropped and held ones that never
became a task directory — surface before anyone re-triages them. A hit here
means: read the row, don't re-derive the verdict.

Each Verdict cell starts with the exact verdict label from SKILL.md's
verdict table (Eval, Upstream fix, Skill edit + eval, Drop — plus
"(planned)" when triage is done but authoring has not shipped), then a dash
and the detail, so the verdict axis stays greppable as the table grows.
`tests/test_task_authoring.py` asserts the Where column matches the task
directories that actually exist.

| Date | Feedback id | Finding | Verdict | Where |
| --- | --- | --- | --- | --- |
| 2026-08-05 | bca74ecdb803 | headerTransparent + automatic content-inset cold-launch bug | Skill edit + eval — guidance misled, but the inset behavior is Apple-owned; skill text fixed upstream | feedback-01-transparent-header-content-inset |
| 2026-08-05 | bca74ecdb803 | styled multi-color title must keep native stack header | Eval | feedback-02-styled-title-keeps-native-stack |
| 2026-08-06 | 4111d2c27a14 | eas-cli capability sync disables iCloud for kvstore-only apps | Upstream fix — Expo-owned CLI bug, ground truth inverts on fix; the agent succeeded in diagnosing it | eas-cli issue/PR (to file) |
| 2026-08-06 | 911b52e0e368 | %-height grid cards + sticky header coupled to native Animated.Value across freezeOnBlur | Eval | feedback-03-shop-grid-sticky-header |
| 2026-08-12 | 029b2a2da3d2 | overlapping RN Modals leave invisible touch-eating layer (iOS, deterministic absorbing state; RN wontfix #50399) | Eval — authored + calibrated (empty=0, baseline=0, reference=1.0, distractor=0.0; two stable judged runs); later simbench variant candidate | feedback-04-modal-editor-touch-freeze |
| 2026-08-12 | 3892d1c10f3c | slider 5.0.1 falsy-zero: value={0} reset never reaches native (also in latest 5.2.0; no prepareForRecycle) | Eval + upstream fix — authored + calibrated (empty=0, baseline=0, reference=1.0, distractor=0.5; two stable judged runs); react-native-slider issue still to file; possible later simbench variant (drag/release + accumulated-state check) | feedback-05-slider-relative-recenter |
| 2026-08-12 | 1610fc625460 | live child reorder + layout transitions mid-drag glitches sortable grid (inherent: commit-driven snapshots vs continuous gesture) | Eval — authored + calibrated (empty=0, baseline=0, reference=1.0, distractor=0.25; two stable judged runs); simbench graduation unlikely near-term (long-press drag driving unreliable) | feedback-06-sortable-grid-stable-layers |
| 2026-08-12 | 019ff4bd-822c-73bf-b6ba-347abc419af5 | EAS Hosting Worker subrequest budget blown by unbatched calendar sync | Eval (planned) — upgraded from hold: public docs pin accounting + Google batch arithmetic; stipulate budget B in the mock, never hard-code plan limits (1,000→10,000 changed 2026-02-11); pending a verifier-shape decision (rubric-judged vs executable fetch-counting) | feedback-07 (planned) |
