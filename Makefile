# One target per step. `make help` lists them.
SHELL := /bin/sh
PY := uv run python

.PHONY: help setup hooks data-metar report-metar gemma-pull bench-gemma tabpfn-smoke test lint

help:  ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: hooks  ## Create the Python 3.12 env and install git hooks
	uv sync

hooks:  ## Install the pre-commit secret check (Entire manages the other git hooks)
	cp scripts/check-secrets.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

data-metar:  ## Download all VOBL METARs from IEM (skips years already on disk)
	$(PY) -m cloudsea.data.iem

report-metar:  ## Phase 0 coverage + dawn fog frequency report
	$(PY) -m cloudsea.data.metar_report

gemma-pull:  ## Pull the pinned Gemma 4 build into the local Ollama (and fetch CC test photos)
	ollama pull $${GEMMA_MODEL:-gemma4:e2b-it-q4_K_M}
	$(PY) -m cloudsea.bench.fetch_test_photos

bench-gemma:  ## Benchmark Gemma on the Ollama at OLLAMA_URL (LABEL=name-for-results)
	$(PY) -m cloudsea.bench.gemma_bench $(if $(LABEL),--label $(LABEL))

tabpfn-smoke:  ## Check the TabPFN API key and report the served model
	$(PY) -m cloudsea.bench.tabpfn_smoke

test:  ## Run unit tests
	uv run pytest -q

lint:
	uv run ruff check cloudsea tests
