# Harbor is a locked dependency, so plain `uv run harbor` uses the pinned
# release. To develop against a local Harbor checkout instead, prefix any
# target with HARBOR_WITH="--with ../harbor".
HARBOR_WITH ?=

.PHONY: help test check codegen-calibrate codegen-oracle codegen-baseline codegen-judge codegen-models codegen-muse simbench-ladder simbench-hard simbench-unguided simbench-flows simbench-muse simbench-calibrate report viewer export

# The default target describes commands; it never starts an evaluation.
help:
	@echo "Read README.md and docs/repository-map.md for the layout."
	@echo "Safe checks: make test; make check"
	@echo "Results: make viewer; make report; make export"
	@echo "Evaluation targets use model tokens and/or simulator compute. See docs/run-and-read-evaluations.md."

test:
	uv run pytest -q

check:
	uv run expo-eval-suite check

# Deterministic-guard and judge calibration over every expo-codegen task:
# empty and unchanged workspaces must guard to 0 without a judge call; the
# reference solution must judge to 1.0; a solution/distractor/ (plausible-but-
# wrong fix), where present, must fail its declared criteria. A commented
# baseline also goes through the real judge (judged brackets need
# credentials, like codegen-judge). Run after any rubric, prompt, or runner
# change. While authoring one task: --only <task-dir-name>.
codegen-calibrate:
	uv run expo-codegen-calibrate

codegen-oracle:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen/reference-smoke.yaml --job-name codegen-oracle --yes

codegen-baseline:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen/baseline-smoke.yaml --job-name codegen-baseline --yes

# Real LLM-judged run of baseline (nop) and oracle agents across every
# expo-codegen task. Needs judge credentials: either a provider API key for the
# default LiteLLM judge, or REWARDKIT_JUDGE=claude-code to use a logged-in
# claude CLI.
codegen-judge:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen/judge.yaml --job-name codegen-judge --yes

# Model/effort ladder (haiku/sonnet/opus/fable at low effort + haiku at high)
# using the host's logged-in claude CLI for both agents and judge.
codegen-models:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen/models.yaml --job-name codegen-models --yes

# Muse Code (Meta) cells over the expo-codegen tasks, judged like
# codegen-models. Requires a logged-in muse CLI on the Standard tier (the
# Contributor default trains on submitted data — see jobs/codegen/muse.yaml).
codegen-muse:
	uv run $(HARBOR_WITH) harbor run -c jobs/codegen/muse.yaml --job-name codegen-muse --yes

# Simulator-use benchmark: (model x driver-tool) cells on golden apps with
# nop floor + scripted oracle ceiling. Requires macOS + Xcode simulators +
# agent-device CLI + logged-in claude. Rerunning a target resumes its
# pending trials in runs/<job-name>.
simbench-ladder:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench/ladder.yaml --job-name simbench-ladder --yes

simbench-hard:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench/hard.yaml --job-name simbench-hard --yes

# Unguided condition over the ladder tiers; tools remain installed.
# This measures guidance/discovery, not the effect of removing a tool.
simbench-unguided:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench/unguided.yaml --job-name simbench-unguided --yes

# Flow tier: journal-sequence-verified multi-step flow (see CONTRIBUTING).
simbench-flows:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench/flows.yaml --job-name simbench-flows --yes

# Muse Code (Meta) x driver-tool cells over the ladder tiers + flow task;
# floors/ceilings live in the ladder/flows runs (merge reports to compare).
# Keep local resource concurrency bounded as with the other simbench targets.
simbench-muse:
	uv run $(HARBOR_WITH) harbor run -c jobs/simbench/muse.yaml --job-name simbench-muse --yes

report:
	uv run expo-eval-report runs/codegen-judge runs/codegen-models -o outputs/eval-report.html

# Local web viewer over runs/: browse every eval, watch live runs come in.
viewer:
	uv run expo-eval-viewer

# Append finished runs to the git-tracked results history (viewer renders it).
export:
	uv run expo-eval-export

simbench-calibrate:
	uv run expo-simbench-calibrate
