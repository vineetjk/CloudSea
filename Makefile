# One target per step. `make help` lists them.
SHELL := /bin/sh
PY := uv run python

.PHONY: help setup hooks data data-metar data-openmeteo report-metar label-report gemma-pull bench-gemma bench-render tabpfn-smoke test lint

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

data-openmeteo:  ## Summit-column humidity (labels, 2021+) and daily 00 UTC ECMWF runs (features, 2024-03+)
	$(PY) -m cloudsea.data.openmeteo both

data: data-metar data-openmeteo  ## All downloads (cached; reruns fetch only what's new)

label-report:  ## Phase 1: label definitions, base rates, examples, photo check -> docs/phase1/label_report.md
	$(PY) -m cloudsea.analysis.label_report

gemma-pull:  ## Pull the pinned Gemma 4 build into the local Ollama (and fetch CC test photos)
	ollama pull $${GEMMA_MODEL:-gemma4:e2b-it-q4_K_M}
	$(PY) -m cloudsea.bench.fetch_test_photos

bench-gemma:  ## Benchmark Gemma on the Ollama at OLLAMA_URL (LABEL=name-for-results)
	$(PY) -m cloudsea.bench.gemma_bench $(if $(LABEL),--label $(LABEL))

bench-render:  ## Benchmark Gemma on Render 4c-8g and 2c-8g, then delete the services (costs ~$1)
	$(PY) -m cloudsea.bench.render_bench

tabpfn-smoke:  ## Check the TabPFN API key and report the served model
	$(PY) -m cloudsea.bench.tabpfn_smoke

test:  ## Run unit tests
	uv run pytest -q

lint:
	uv run ruff check cloudsea tests
