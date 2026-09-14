# Review tasks in the browser

The task library is a website generated from the actual repository files. It
lets a reviewer inspect a task before spending anything on an evaluation.
Keep this website local. Do not deploy it or upload this repository to a hosting
service unless the user explicitly requests that in a later instruction.

```sh
uv sync --dev
make catalog
open outputs/catalog/index.html
```

The generated HTML includes the task data, JavaScript, CSS, font files and
licenses. It works offline and can be shared as one file. No Expo token, feedback
MCP connection or model API key is required. Regenerate it after changing tasks;
the file is a snapshot, not a live connection to GitHub or the feedback service.

For a local server that also browses recorded runs:

```sh
make viewer
# Tasks: http://127.0.0.1:4477/tasks
# Runs:  http://127.0.0.1:4477/
```

The viewer works before the first evaluation exists. Its task route reads the
current repository on each page load. Use `--repo /path/to/checkout` with
`expo-eval-viewer` or `expo-eval-catalog` when running elsewhere.

## Walk through a task

1. Choose a task set, search for a behavior, or filter writing/repair tasks
   separately from fixed-app device operation.
2. Open a task and read the request the agent receives. The flow explains the
   starting app, agent action, verifier and evidence.
3. Inspect the acceptance criteria, weights, starting source, reference fixes
   and wrong-fix controls. The slider's intentionally vendored wrapper is
   included because reading it is part of that task.
4. Read the motivation, declared control expectations, verifier implementation
   and calibration limitations. A reference file is not proof of calibration.
5. Select **Prepare review**, edit the proposed task prompt, add review notes,
   then **Copy review context** into a coding session with this repository.

The copied context contains both prompts, rubric descriptions, control
expectations, task ID, a definition fingerprint and file paths. It asks the
coding agent to preserve valid alternative solutions and run offline checks.
It does not start an evaluation, edit Git files or push a commit.

Drafts persist in that browser. If a regenerated site changes the task's prompt,
rubric, metadata or control files, an older draft is flagged for reconciliation.
Reset draft returns to the current prompt. If clipboard access is unavailable,
the site selects the generated context for manual copying. Task URLs use stable
IDs in the hash, so individual tasks and sections can be bookmarked.

## Reading coverage honestly

The catalog separates **21 coding tasks**, **seven device-operation tasks**,
and **three experimental native profiles** attached to existing coding tasks.
It displays definitions, not fabricated evaluation results. Native profiles
still need calibration. The three new source tasks also await judge calibration;
existing source comparisons deliberately remain at 18 tasks.

The feedback view explains which reports became tasks, were already covered,
need evidence, remain candidates, or belong outside this suite. Its 17 records
are the repository's reviewed snapshot. New service messages may make those
reviews stale; use the MCP's review-state filter during the next maintenance pass.

## Implementation and design

`src/expo_harbor_evals/catalog.py` reads definitions and embeds them into the
template and assets in `src/expo_harbor_evals/web/`. There is no second task
database or separate frontend application to synchronize. The existing report
and viewer reuse its bundled theme. Presentation files are excluded from the
evaluator implementation fingerprint.

The design follows the Expo Universe website's compact sidebar, restrained
panels, semantic light/dark colors, Inter and JetBrains Mono, and copy-as-prompt
handoff. Color values come from `@expo/styleguide-base` 3.3.0. Asset licenses are
included in every generated HTML file. The layout adapts to smaller screens and
supports keyboard focus, a modal dialog, reduced motion and empty search states.

The local viewer binds to `127.0.0.1`. In Conductor, use the workspace's allocated
port to keep concurrent workspaces separate:

```sh
uv run expo-eval-viewer --port "$CONDUCTOR_PORT"
# Open http://127.0.0.1:<the printed port>/tasks
```

No hosting configuration is needed. The standalone HTML includes prompts and
hidden reference solutions; keep it with reviewers rather than including it in
a benchmark agent's workspace.

`tests/test_catalog.py` checks coverage, source escaping, portable assets,
definition revisions, filtering and copied context. React/Yoga control tests
live in `tests/contracts/` and use pinned dependencies. None of these checks
invoke a model, build a native app or start a simulator.
