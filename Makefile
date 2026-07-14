HARBOR_SRC ?= ../harbor
CALLSTACK_EVALS_SRC ?= ../callstack-evals

.PHONY: fixture partial callstack-import callstack-oracle callstack-baseline

fixture:
	uv run --with $(HARBOR_SRC) harbor run -c jobs/local-fixture.yaml --job-name local-fixture --yes

partial:
	uv run --with $(HARBOR_SRC) harbor run -c jobs/local-partial.yaml --job-name local-partial --yes

callstack-import:
	uv run expo-callstack-import --source $(CALLSTACK_EVALS_SRC)

callstack-oracle:
	uv run --with $(HARBOR_SRC) harbor run -c jobs/callstack-oracle.yaml --job-name callstack-oracle --yes

callstack-baseline:
	uv run --with $(HARBOR_SRC) harbor run -c jobs/callstack-baseline.yaml --job-name callstack-baseline --yes
