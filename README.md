# Expo Harbor Evals

Standalone Harbor tasks and utilities for Expo and React Native agent evals.

This repo intentionally **does not fork Harbor**. Harbor remains the eval runner:
jobs, trials, agents, logs, reward aggregation, and result viewing. This repo owns
the Expo-specific task definitions and the small adapter that turns an Expo
`eval-out/result.json` into Harbor's numeric `/logs/verifier/reward.json`.

## Why Not Fork Harbor?

Fork Harbor only when the core framework has to change. For this work, Harbor's
existing contract is enough:

1. A task has `instruction.md`, `task.toml`, `environment/`, and `tests/test.sh`.
2. Harbor runs `tests/test.sh`.
3. Harbor reads `/logs/verifier/reward.json`.

The iOS simulator/EAS workflow should be a producer of evaluator `result.json`,
not a new Harbor data model.

## Repository Shape

```text
jobs/                         Harbor job configs
src/expo_harbor_evals/        Development helpers
tasks/expo-mobile-eval-import Harbor task that normalizes evaluator output
tasks/callstack-*              Imported React Native code-generation tasks
third_party/                   Upstream license and pinned-source metadata
```

## Callstack React Native Evals

The repo includes an importer for selected tasks from
[`callstackincubator/evals`](https://github.com/callstackincubator/evals). The
default cohort contains nine Expo tasks across `expo-sdk`, `expo-router`, and
`expo-ui`:

```bash
make callstack-import
```

Each upstream eval becomes a normal Harbor task. The prompt and baseline app are
the agent input, the reference implementation becomes the Harbor oracle, and
the weighted requirements become a provider-neutral Rewardkit rubric.

Run all nine oracle solutions without Docker or API keys:

```bash
make callstack-oracle
```

This uses exact reference comparison only as an import/plumbing smoke test. It
is intentionally separate from real scoring because valid agent solutions do
not need to match the reference source text.

For a real agent run, use the normal `judge` verifier mode and pass a LiteLLM
judge plus its provider credential. For example:

```bash
uv run --with ../harbor harbor run \
  --path tasks \
  --include-task-name 'callstack-expo-*' \
  --agent codex \
  --model YOUR_AGENT_MODEL \
  --verifier-env REWARDKIT_JUDGE=YOUR_LITELLM_JUDGE \
  --verifier-env OPENAI_API_KEY="$OPENAI_API_KEY" \
  --yes
```

The imported tasks preserve upstream requirement IDs, descriptions, weights,
commit provenance, and MIT attribution. Use `--all-expo` with
`expo-callstack-import` when the first cohort is stable enough to expand from 9
to all upstream Expo tasks.

## Local Smoke Without Docker

This machine did not have Docker available during the spike, so the repo includes
a tiny dev-only Harbor environment:

```text
expo_harbor_evals.local_env:LocalHostEnvironment
```

It maps Harbor paths (`/logs`, `/tests`, `/solution`, `/app`) into a per-trial
host directory. It is not a sandbox.

From this repo:

```bash
uv run --with ../harbor \
  harbor run -c jobs/local-fixture.yaml --job-name local-fixture --yes
```

Expected: one trial, zero exceptions, `reward=1.0`.

Partial-score smoke:

```bash
uv run --with ../harbor \
  harbor run -c jobs/local-partial.yaml --job-name local-partial --yes
```

Expected: one trial, zero exceptions, `reward=0.5`.

## Docker/Real Harbor Shape

On a machine with Docker:

```bash
uvx harbor run \
  --path tasks \
  --include-task-name expo-mobile-eval-import \
  --agent nop \
  --env docker \
  --yes
```

## EAS Bridge Direction

Keep EAS/macOS/iOS simulator execution outside Harbor's core. Feed the resulting
`eval-out/result.json` into the same scorer:

```bash
uv run expo-eval-score eval-out/result.json reward.json --details details.json
```

Inside Harbor, set `EVAL_RESULT_PATH` or make `MOBILE_EVAL_COMMAND` produce
`/logs/verifier/mobile-eval/result.json`.
