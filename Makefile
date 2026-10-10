# One target per step. `make help` lists them.
SHELL := /bin/sh
PY := uv run python

.PHONY: backtest train-table nightly grade help setup hooks data data-metar data-openmeteo report-metar label-report gemma-pull bench-gemma bench-render tabpfn-smoke test lint

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

backtest:  ## Phase 2: TabPFN vs baselines on the 2025-26 season -> docs/results/backtest.json
	$(PY) -m cloudsea.model

train-table:  ## Freeze labelled rows into data/model/train_table.parquet (read by the nightly job)
	$(PY) -c "from cloudsea.model import save_train_table; save_train_table()"

nightly:  ## Make tonight's call (add ARGS=--dry-run to print instead of saving)
	$(PY) -m cloudsea.jobs.nightly $(ARGS)

grade:  ## Grade this morning's dawn (ARGS=--dry-run to print only)
	$(PY) -m cloudsea.jobs.grader $(ARGS)

screenshots:  ## Screenshots of the live app and share cards -> docs/screenshots (CHROMIUM=path if needed)
	uv run --with playwright==1.56.0 python scripts/screenshots.py

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

# --- Phase 3: API and local Postgres ---
.PHONY: db-up db-down api test-db
LOCAL_DB := postgresql://postgres:cloudsea@localhost:5432/cloudsea
TEST_DB := postgresql://postgres:cloudsea@localhost:5432/cloudsea_test

db-up:  ## Start local Postgres 16 in docker (docker-compose.yml), plus a cloudsea_test DB
	docker compose up -d --wait db
	docker compose exec -T db psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'cloudsea_test'" | grep -q 1 \
		|| docker compose exec -T db createdb -U postgres cloudsea_test

db-down:  ## Stop local Postgres (data stays in the docker volume)
	docker compose down

api:  ## Run the API on :8000 with reload (uses DATABASE_URL, default the local docker DB)
	DATABASE_URL=$${DATABASE_URL:-$(LOCAL_DB)} uv run uvicorn cloudsea.api.main:app --reload --port 8000

test-db:  ## All tests, including Postgres integration tests (drops tables in the cloudsea_test DB)
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(TEST_DB)} uv run pytest -q
