# ════════════════════════════════════════════════════════════════════
# N100 Financial Intelligence Platform — Makefile
# Sprint 1: Data Foundation
# Author: CH Kaushik
# ════════════════════════════════════════════════════════════════════

.PHONY: setup load validate ratios test report dashboard api clean all help

PYTHON := python3
PIP := pip3
DB := nifty100.db
VENV := venv

# ─── Help ───────────────────────────────────────────────────────────
help: ## Show available targets
	@echo "╔══════════════════════════════════════════════════════════╗"
	@echo "║   N100 Financial Intelligence Platform — Makefile       ║"
	@echo "╚══════════════════════════════════════════════════════════╝"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ─── Setup ──────────────────────────────────────────────────────────
setup: ## Create venv and install dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/$(PIP) install --upgrade pip
	$(VENV)/bin/$(PIP) install -r requirements.txt
	@mkdir -p output db src/etl tests/etl notebooks
	@echo "✅ Environment ready"

# ─── Data Loading ───────────────────────────────────────────────────
load: ## Load all 12 Excel files into SQLite (nifty100.db)
	$(PYTHON) -m src.etl.loader
	@echo "✅ Data loaded into $(DB)"

# ─── Validation ─────────────────────────────────────────────────────
validate: ## Run 16 DQ rules and generate validation_failures.csv
	$(PYTHON) -m src.etl.validator
	@echo "✅ Validation complete — see output/validation_failures.csv"

# ─── Ratios ─────────────────────────────────────────────────────────
ratios: ## Calculate and load financial ratios (Sprint 2)
	@echo "⏳ Ratios module — Sprint 2"

# ─── Testing ────────────────────────────────────────────────────────
test: ## Run all unit tests with coverage
	$(PYTHON) -m pytest tests/ -v --tb=short
	@echo "✅ All tests passed"

# ─── Report ─────────────────────────────────────────────────────────
report: ## Generate analysis reports (Sprint 3)
	@echo "⏳ Report module — Sprint 3"

# ─── Dashboard ──────────────────────────────────────────────────────
dashboard: ## Launch dashboard UI (Sprint 4)
	@echo "⏳ Dashboard module — Sprint 4"

# ─── API ────────────────────────────────────────────────────────────
api: ## Start REST API server (Sprint 5)
	@echo "⏳ API module — Sprint 5"

# ─── Clean ──────────────────────────────────────────────────────────
clean: ## Remove database and generated files
	rm -f $(DB)
	rm -f output/*.csv output/*.json
	rm -rf __pycache__ src/__pycache__ src/etl/__pycache__ tests/__pycache__ tests/etl/__pycache__
	@echo "🧹 Cleaned"

# ─── All ────────────────────────────────────────────────────────────
all: load validate test ## Run full pipeline: load → validate → test
	@echo "🎉 Sprint 1 pipeline complete"
