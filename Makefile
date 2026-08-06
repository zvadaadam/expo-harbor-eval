# Harbor is a locked dependency, so plain `uv run harbor` uses the pinned
# release. To develop against a local Harbor checkout instead, prefix any
# target with HARBOR_WITH="--with ../harbor".
HARBOR_WITH ?=
CALLSTACK_EVALS_SRC ?= ../callstack-evals

.PHONY: test fixture partial codegen-import codegen-calibrate codegen-oracle codegen-baseline codegen-judge codegen-models simbench-ladder simbench-hard report viewer export

test:
	uv run pytest -q

fixture:
	uv run $(HARBOR_WITH) harbor run -c jobs/local-fixture.yaml --job-name local-fixture --yes

partial:
	uv run $(HARBOR_WITH) harbor run -c jobs/local-partial.yaml --job-name local-partial --yes

codegen-import:
	uv run expo-codegen-import --source $(CALLSTACK_EVALS_SRC)

# Deterministic-guard and judge calibration over every expo-codegen task:
# empty and unchanged workspaces must guard to 0 without a judge call; the
# reference solution must judge to 1.0; a solution/distractor/ (plausible-but-
# wrong fix), where present, must judge below 1.0 (judged brackets need
# credentials, like codegen-judge). Run after any rubric, prompt, or runner
# change. While authoring one task: --only <task-dir-name>.
codegen-calibrate:
	uv run expo-codegen-calibrate

codegen-oracle:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen-oracle.yaml --job-name codegen-oracle --yes

codegen-baseline:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen-baseline.yaml --job-name codegen-baseline --yes

# Real LLM-judged run of baseline (nop) and oracle agents across every
# expo-codegen task. Needs judge credentials: either a provider API key for the
# default LiteLLM judge, or REWARDKIT_JUDGE=claude-code to use a logged-in
# claude CLI.
codegen-judge:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen-judge.yaml --job-name codegen-judge --yes

# Model/effort ladder (haiku/sonnet/opus/fable at low effort + haiku at high)
# using the host's logged-in claude CLI for both agents and judge.
codegen-models:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen-models.yaml --job-name codegen-models --yes

# Simulator-use benchmark: (model x driver-tool) cells on golden apps with
# nop floor + scripted oracle ceiling. Requires macOS + Xcode simulators +
# agent-device CLI + logged-in claude. Rerunning a target resumes its
# pending trials in runs/<job-name>.
simbench-ladder:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench-ladder.yaml --job-name simbench-ladder --yes

simbench-hard:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench-hard.yaml --job-name simbench-hard --yes

# No-tool baseline over the ladder tiers (neutral simctl-only preface);
# merge with the ladder run to see how much of a score the tool is worth.
simbench-notool:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench-notool.yaml --job-name simbench-notool --yes

# Flow tier: journal-sequence-verified multi-step flow (see CONTRIBUTING).
simbench-flows:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench-flows.yaml --job-name simbench-flows --yes

report:
	uv run expo-eval-report runs/codegen-judge runs/codegen-models -o outputs/eval-report.html

# Local web viewer over runs/: browse every eval, watch live runs come in.
viewer:
	uv run expo-eval-viewer

# Append finished runs to the git-tracked results history (viewer renders it).
export:
	uv run expo-eval-export
