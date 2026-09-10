# Running mobile evaluations locally and on EAS

The cloud path uses EAS Workflows directly: a macOS worker runs the simulator,
Harbor and verifier together. Local execution uses Xcode on your Mac. Both use
the same benchmark app sources and task checks.

For submitted Expo app builds and the three experimental native repair scenarios,
see [Evaluation quality and native app checks](evaluation-quality.md).
For the smallest model pilot, cost boundaries and report interpretation, see
[Run a small pilot and read the evidence](run-and-read-evaluations.md).

Expo Sandbox MCP and E2B are not dependencies. A separately leased EAS Simulator
session through `eas simulator:*` is a different execution path and is not yet
wired into the state-scored evaluator; the current workflow owns its simulator.

## Configuration

From the repository root:

```sh
uv sync --dev
cp .env.example .env.local  # first setup only; preserve any existing file
```

Fill in `.env.local`:

| Variable | Required for | Value |
|---|---|---|
| `EXPO_TOKEN` | Token-based EAS authentication | Expo access token for the evaluation account/organization |
| `EAS_EVAL_PROJECT_ID` | Preparing an EAS run | Existing EAS project's UUID, not its slug |

Create the token in [Expo account settings](https://expo.dev/settings/access-tokens).
Use an evaluation project whose account has access to EAS Workflows/macOS compute.
Find its UUID in the project's dashboard settings or `extra.eas.projectId` in
an already linked app's config. Project creation is a one-time setup outside
this runner; `prepare` links the generated payload to that existing UUID.

`expo-eas-eval` automatically reads `.env`, then `.env.local`, from the current
working directory. Exported variables override both files, and `--project-id`
overrides `EAS_EVAL_PROJECT_ID`. Only the two listed settings are loaded; values
are literal, with no shell execution or variable interpolation. Run commands
from this repository root even when `--project` points to a prepared payload.
Other commands, including raw `npx eas-cli`, do not use this loader.

`.env` and `.env.*` are gitignored, with `.env.example` the tracked template.
Environment files are excluded from prepared cloud uploads. The controller uses
the token to contact EAS; the workflow removes the EAS token from the calibration
process environment. Supply these same variables through the environment in CI.
An existing EAS CLI login also works in place of `EXPO_TOKEN`.

The cloud controller needs `uv`, Git and Node.js with `npx` (Node 24 is the
reference version). It does not need local Xcode: the EAS worker installs its
own evaluation tools. Local simulator runs require the Mac prerequisites below.
No model-provider key is required for scripted calibration. Candidate model
runs use their own model authentication separately.

## Local calibration

Prerequisites: macOS, Xcode with an available iPhone 17-compatible iOS runtime,
`uv`, and `agent-device`. The reference tool version for the EAS workflow is
`agent-device@0.19.3`. The vision-grid oracle also requires `argent`.

```sh
uv sync --dev
make simbench-calibrate

# Repeat the flow brackets, or scope to one atomic task:
uv run expo-simbench-calibrate --attempts 2
uv run expo-simbench-calibrate --task simbench-ios-01-goldennotes-create-note
```

Calibration runs actual Harbor trials. It fails unless every no-op scores 0,
every scripted UI oracle scores 1, and every flow negative control completes
the state in the wrong order and scores 0. Failed oracle exits, infrastructure
errors, missing attempts, and cleanup failures also fail calibration.

`--output` selects a new output directory; existing output is never overwritten.
`--timeout` bounds the complete shard (default 2,100 seconds). The default flow
has three conditions per attempt; increase the budget deliberately for large
repetition counts, respecting the cloud worker's time allowance.

`SimbenchEnvironment` creates a disposable simulator for each trial and deletes
only that device afterward. `SIMBENCH_DEVICE` is its UDID;
`SIMBENCH_DEVICE_NAME` is the unique name needed by agent-device's `--device`.
`AGENT_DEVICE_SESSION` is also unique per trial. Set `SIMBENCH_RUNTIME` to an
installed runtime identifier or version when pinning the OS. With no pin, the
environment chooses the newest compatible installed runtime and records it.
Existing `make simbench-*` model jobs now use this environment.

The environment retains the local seatbelt development isolation model: the
candidate uses installed host tools/configuration. Host Claude and Muse commands
now hide local evaluator answers and owned app-state containers from ordinary
file reads, but other host files and services remain accessible.
It is not a hardened environment for adversarial or untrusted benchmark agents.

## Evidence and replay

Each successful collection writes `verifier/evidence/manifest.json` and a
`Documents/` snapshot into the Harbor trial. The app is stopped before collection.
Absent fresh-app state is recorded explicitly; corrupt files fail collection.
The manifest records the task, trial, bundle, backend, device and file hashes.
Device/runtime metadata and source/binary hashes are in `artifacts/`.

Replay a saved snapshot on any machine with Python, without a simulator:

```sh
python3 tasks/simbench/simbench-ios-07-goldennotes-shift-flow/tests/verify.py \
  /tmp/replayed-reward.json --details /tmp/replayed-details.json \
  --evidence /path/to/trial/verifier/evidence --trial-id ORIGINAL_TRIAL_ID
```

Use the actual trial ID from the original run. Identity or checksum mismatches
produce `sim_runner_ok: 0`, a nonzero exit and an explanation. The hashes detect
corruption and accidental mixing; they do not authenticate an untrusted producer.

The flow reward remains all-or-nothing. Snapshot transport does not convert it
into partial credit. Vision fixtures now randomize their target and count all
wrong taps, so their revised task definition needs fresh calibration.

## Prepare and run an EAS shard

Use a dedicated eval-owned EAS project/account without production secrets.
Authenticate the EAS CLI or supply `EXPO_TOKEN` through the process environment.
Keep credentials out of command arguments and source files.

```sh
# Reads EXPO_TOKEN and EAS_EVAL_PROJECT_ID from .env.local automatically.
uv run expo-eas-eval prepare --output .context/eas-shard

uv run expo-eas-eval run \
  --project .context/eas-shard \
  --output runs/eas-flow-calibration
```

Preparation does not create a project or spend cloud compute. It copies an
allowlisted payload: the selected simbench task, Python modules, dependency
lock, and worker scripts. It creates a separate temporary Git repository with
a source manifest; it does not modify the current branch or upload the whole
developer workspace. `--task` and `--attempts` select the shard. The vision-grid
task is excluded from this workflow because its oracle additionally needs Argent.

The workflow pins `macos-tahoe-26.4-xcode-26.4`, Node 24, uv 0.11.17 and
agent-device 0.19.3; the controller pins EAS CLI 23.2.0. Actual Xcode, tool and
runtime details accompany the evidence. The worker checks source hashes,
runs calibration, and attempts artifact upload even after a failed step.
Hard VM termination can still prevent upload; the in-process budget leaves
time to finish and collect evidence before that boundary.

The controller records the run ID, polls with a deadline, downloads the exact
artifact, rejects unsafe archives and mismatched source/shard manifests, and
rechecks calibration results. It attempts cancellation on failure or timeout.
It does not retry submission automatically: a lost response may already have
created a billed run. If `run.json` remains `submitting` with no run ID, inspect
the project's EAS workflow runs before submitting again.

Recover a download or explicitly cancel a known run:

```sh
uv run expo-eas-eval collect --project .context/eas-shard \
  --run-id RUN_ID --output runs/recovered-eas-flow

uv run expo-eas-eval cancel --project .context/eas-shard --run-id RUN_ID
```

Use a fresh recovery directory. The default controller deadline is 3,600 seconds
including queueing; adjust `--timeout` for the actual account. Workflow and
simulator compute consume the account's allowances.

View a local or downloaded Harbor shard:

```sh
uv run expo-eval-report runs/LOCAL_CALIBRATION/trials \
  runs/eas-flow-calibration/evidence/calibration/trials \
  -o outputs/mobile-calibration.html
```

Reports separate measurements and backend series. Completion counts fully
passing attempts among recorded outcomes, including execution errors; pending
and missing results remain explicit. The secondary mean uses valid rewards.
Click an attempt in the task matrix for checks and recorded evidence. Report
generation reads files and makes no model calls.

## Validation status

Historical validation on September 9, 2026, **before the evaluation-quality
revision**. These results do not certify the changed tasks or new native lane:

- 62 automated tests passed, including evidence replay, result rejection,
  archive validation, source preparation, process/device cleanup and dotenv
  configuration precedence.
- All seven simbench tasks passed real simulator calibration: 18 trials on
  iPhone 17 devices with the recorded iOS 26.5 runtime. Each atomic task had a
  no-op and oracle trial; the flow had two attempts each for no-op, ordered
  oracle and the wrong-order negative control.
- A saved real flow snapshot replayed with Python alone and retained reward 1.
- All 18 trial-owned simulators were deleted after completion.
- The external-import Harbor fixtures retained rewards 1.0 and 0.5.
- The EAS workflow validated against Expo's current published workflow schema.

Live EAS dispatch has not been validated: this environment was not logged into
EAS and no eval-owned project was supplied.
The workflow runs simbench calibration or verifies an already-written Expo
candidate. Provisioning cloud coding agents and their model credentials is
subsequent work. Three codegen tasks have an experimental native path; see
[its calibration requirements](evaluation-quality.md). The revised source judge,
randomized vision fixture and native lane have not been run on this revision.
