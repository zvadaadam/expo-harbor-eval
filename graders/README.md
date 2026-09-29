# Grading kit

Harbor runs tasks. **Harbor RewardKit evaluates checks and combines their
scores.** [catalog.json](catalog.json) is the shared catalog for the editor,
exporter, and [runner](kit_runner.py). The adapter calls the pinned upstream
criteria and aggregation functions; it does not maintain a second grader engine.

The editor exposes **all 23 built-in criteria in the pinned RewardKit revision**,
plus AI review, a convenient test-script wrapper, and custom Python criteria.
A parity test compares the catalog and every configurable argument against the
installed upstream package so omitted checks cannot silently regress.

| Group | Available checks |
| --- | --- |
| AI review | Binary, Likert/rating, or numeric source assessment |
| Tests & commands | Node/Python assertions, custom `@criterion`, exit status, stdout text/exact/regex |
| Files & text | Exists, absent, contains, regex, exact text, two-file equality, text similarity |
| Structured data | JSON key/path, CSV cell, Excel cell, SQLite query |
| Images | Dimensions, pixel similarity |
| HTTP | GET status, response text |
| Agent trajectory | Tool used, tool not used, turn budget |

Each check has its own requirement and typed settings. Optional settings use
RewardKit defaults. Advanced scoring offers weighted average, weighted sum,
all-pass, any-pass, threshold, and required-pass, with weights, negation, and
optional checks. Similarity/turn-budget/custom criteria retain fractional
scores. Likert and numeric AI outputs are normalized by RewardKit.

`all-pass`, `any-pass`, and `required-pass` consider a score **above zero** a
pass, matching upstream semantics. Use binary checks for strict pass/fail.
Weighted sum emits raw totals (potentially outside 0–1); negative weights are
supported only with that aggregation. Do not compare totals from different
rubrics. Calibration expects full credit for positive criteria and zero for
negative-weight penalties. A negative control must score below the ideal total
and fail its declared `must_fail` checks: zero for positive-weight requirements,
or one for negative-weight penalty detectors.

## Author a coding task

1. Enter a title, prompt, and requirement in **Create a task**.
2. Pick a check from the grouped **Check with** selector; mix methods as needed.
3. Save whenever you like. Saving never runs a test or judge.
4. Add starting code and correct/wrong examples. Select which checks must
   reject the wrong answer and comment-only baseline.
5. **Save & export task** writes a self-contained Harbor task outside the active
   library. Review it, then run `uv run expo-codegen-calibrate --tasks <export-parent>`.
   Programmatic checks need no judge; AI review consumes the configured judge's usage.

**Tests pass** creates a deliberately failing `.cjs` placeholder in **Test files**.
The script receives the absolute submission directory as its first argument
and must exit zero within 30 seconds. **Custom Python criterion** creates a
`.py` placeholder with a RewardKit `@criterion` function. Name that function in
the check's settings and return a boolean or a normalized score in [0, 1].
Errors remain execution errors, not candidate failures.

Command checks run in the submission directory, with an optional relative
working directory and timeout. HTTP checks run from the verifier; a candidate
server in a separate container is not automatically reachable on localhost.
Image/Excel dependencies are included in the locked environment and exported
runner's script dependencies.

Trajectory checks transfer `/logs/agent/trajectory.json` as an explicit Harbor
artifact into the separate verifier. A relative trajectory path refers to a
fixture under `tests/checks/`, never an arbitrary host file. The selected agent
must actually produce an ATIF trajectory; missing evidence scores zero. This
records tool usage, not proof that app behavior works or tamper-proof evidence.

Test files stay under `tests/checks/`, outside the candidate workspace.
Programmatic checks do not inherit model credentials or Node/Python interpreter
hooks. Execution isolation comes from the Harbor environment; trusted task
commands and custom criteria are executable code.

## Author a simulator task

Choose **Simulator tasks** under Task settings, or duplicate one from the library.
Select one of the ten existing scenarios, then adapt its prompt, `verify.py`,
and reference `oracle.py`. App source is available in a collapsed section.
The scenario-type selector includes all eleven simulator tiers in the repository,
including forms, scrolling, gestures, async flows, and three sign-in surfaces.

Export copies the complete native fixture, preserving its driver, evidence
collector, and executable scripts. The template fingerprint prevents a changed
fixture from being silently copied beneath a draft. A held template stays held.
Simulators use their existing app-state/UI-event verifier rather than a coding
source judge. Preserve event checks so injected state cannot pass.

Exports include `calibration.yaml` with no-op, UI oracle, and any template-specific
negative controls. On a Mac with Xcode and the required simulator driver, run:

```sh
uv run harbor run -c <exported-task>/calibration.yaml --job-name <unique-name> --yes
```

Review the no-op and oracle rewards and infrastructure checks before admitting
the task to a suite. Exporting does not boot a simulator or establish calibration.
The calibration job explicitly opts into unversioned draft execution. This never
bypasses fingerprint checks for tasks already in the locked suite or under `tasks/`.
The job file contains local absolute paths; regenerate its dataset path when
moving the task to a different checkout.

## Evidence and editing

Default AI-only tasks retain the canonical source runner. Other scoring plans
also carry `tests/requirements/grading.json`, a catalog snapshot, the kit runner,
and `tests/source_runner.py`. Every check remains individually named in
`reward-details.json`; mixed scoring aggregates individual criteria once.
Empty/unchanged coding submissions guard to zero without a judge. A runner or
judge error publishes no candidate reward. Source, mixed, and programmatic
measurements have separate identities; none claim native UI verification.

**Edit** updates a library task with conflict detection and rollback, refreshes
its baseline/reference copies, marks it as needing calibration, and updates only
its definition hash in the suite. Existing policy/native verifier recipes remain
protected. Direct editing of an existing simulator task still changes its prompt
and metadata; use **Duplicate** to author a new simulator scenario and verifier.

The picker covers the complete **built-in criterion catalog**, not every
RewardKit configuration surface. Arbitrary nested reward directories, MCP judge
servers, and multi-agent judge orchestration remain code-level configurations.
See the [pinned upstream source](https://github.com/harbor-framework/harbor/tree/cfc54c995e90cd438deb862189a58053b9d89fd3/packages/rewardkit).
