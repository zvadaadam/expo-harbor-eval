# Harbor Studio

A local workbench for this repository's Expo evaluations. Built with **TanStack
Start, Router, and Query**, React, Zustand, and Zod. The visual system follows
the current Expo website's dashboard components: its sidebar, page headers,
project tiles, pill controls, and Inter/JetBrains Mono typography. It uses the
actual **@expo/styleguide 14.4.0 CSS theme** and **@expo/styleguide-icons 4.4**.
The theme and wordmark are vendored with their license; see
[the source notes](src/vendor/expo-styleguide/README.md). The frontend does not
depend on Next.js or the Expo website checkout.

## Start

From the repository root, with Node.js 22.12+ and Python 3.12+:

```sh
uv sync --frozen
npm --prefix studio ci
make studio
```

Open **http://127.0.0.1:4747**. Launching Studio makes no model calls and starts
no simulator. A fresh checkout without `runs/` still shows every task definition.
Use `STUDIO_PYTHON=/absolute/path/to/venv/bin/python make studio` to select another
evaluator environment. Execution checks that its Harbor version matches the
repository pin. Node.js 24+ is needed for policy controls.

For a production build served locally:

```sh
npm --prefix studio run build
npm --prefix studio start
```

## What works

- **Task library:** search, category filters, card/list views, prompts, rubrics,
  source files, readiness metadata, and related attempts. Search state is in the URL.
- **Evidence:** existing Harbor and native results, named checks, original logs,
  screenshots, errors, generation usage, regrade lineage, and provenance.
- **Authoring:** one-page creation with automatic task/check IDs, a RewardKit
  picker, and expandable files/examples. Save incomplete drafts and resume them
  later. Revision checks reject stale saves from another tab.
- **Grading kit:** all 23 pinned RewardKit built-ins, AI review, trusted test
  scripts, and custom Python criteria. The grouped picker and exporter share
  [one catalog](../graders/README.md). Fractional scores, AI rating/numeric scales,
  all six aggregation methods, weights, negation, and optional checks are supported.
- **Simulator authoring:** select Simulator tasks and start from any of the ten
  existing fixtures. Edit its prompt, verifier, reference UI automation, and app
  source. All eleven simulator scenario types are available. Exports include a
  complete native fixture and a no-model calibration job with its negative controls.
- **Library editing:** Edit/Run actions in the gallery and task details. Save
  changes back to a task with conflict detection, verifier preservation, rollback,
  and a refreshed task hash. Coding files and requirements are editable;
  simulator tasks expose their prompt and metadata. Edited tasks need calibration.
- **Task export:** generate a complete, reviewable Harbor task folder in
  `outputs/studio/<draft-id>/<revision>/<task-id>/`, using the repository's
  verifier/scaffold templates. It does not overwrite task definitions or change
  frozen suite membership. Review and calibrate before moving it into `tasks/`.
- **Local execution:** deterministic guard checks, policy-contract calibration,
  and Harbor reference smoke jobs. These explicit actions do not call models.
  Jobs serialize on an OS lock, retain logs, support cancellation, and stop after
  ten minutes. Owned descendants are terminated even when they start new sessions.
- **Sonnet planning:** download a one-task Harbor configuration with low, medium,
  or high effort and 1–3 attempts. Run it explicitly from a terminal. Generation
  and judging consume usage; the plan has **no hard dollar cap**.

The editor exports **source-review, programmatic, mixed coding, and simulator tasks**.
Coding duplicates do not inherit legacy policy/native verifiers. Simulator
duplicates retain their complete fixture, but require fresh calibration; a held
scenario stays held. Native execution, paid launch, in-app regrading, and suite
promotion remain CLI/review workflows. The existing `make viewer` on port 4477
and offline reporting tools remain available.

## Data and boundaries

| Path | Purpose |
| --- | --- |
| `tasks/` | Library definitions; editable with task fingerprint checks |
| `runs/` | Existing evidence, plus new Harbor smoke attempts |
| `.studio/drafts/` | Local JSON drafts, outside suite discovery |
| `.studio/jobs/` | Saved control plans, state, logs, cancellation markers |
| `outputs/studio/` | Exported task folders awaiting review |
| `graders/` | Shared RewardKit recipe catalog, adapter, and authoring guide |

`bridge/catalog.py` calls the existing `report.load_runs` normalization; the UI
does not implement scoring. The adapter guards nested reads against symlink
escapes. Artifact previews are restricted to the selected task/attempt, render
text without HTML execution, and limit preview sizes. Start server functions
use Zod validation and same-origin CSRF protection. The app accepts only loopback
hostnames and launches a fixed set of commands using structured argument arrays.
It is a single-user local tool, not a hosted multi-user service.

The Python worker monitors its owning server. Stopping that server interrupts
unfinished controls; their state remains available on the next start. Guard
diagnostics call the canonical deterministic guard functions directly and fail
closed when the baseline is stale. They do not enter the judge execution path.
Local diagnostic logs are separate from benchmark evidence. Harbor smoke runs
retain the normal evaluator identity. Saving a library edit refreshes only that
task's suite hash; creating/exporting a draft leaves the active suite unchanged.
The standalone comparison page is intentionally omitted from the authoring UI.

Missing scores/readiness/usage are shown as missing. Reported usage is generation
usage, excludes unreported judge usage, and is not a subscription invoice.
Controls and regrades are labeled; regrades are not independent generations.
Small exploratory comparisons cannot establish that higher effort improves
performance.

## Development checks

```sh
npm --prefix studio run typecheck
npm --prefix studio test
npm --prefix studio run format:check
npm --prefix studio run build
uv run pytest -q
uv run expo-eval-suite check
```

TypeScript tests exercise revision conflicts, path safety, draft migration,
grader settings, and generated identifiers. Python tests cover real RewardKit
pass/fail controls, mixed weights, export schemas, task editing and rollback,
verifier preservation, evidence, and process-tree cancellation. They use
temporary fixtures and do not invoke a model.

TanStack Router generates `src/routeTree.gen.ts` during Vite startup/build. Keep
it committed for type checking after a fresh install. Query owns repository
data and mutations; a separate Zustand store owns each editor session. Server
filesystem/process code remains in `src/server/` and the Python bridge.
