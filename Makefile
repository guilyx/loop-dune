# Developer shortcuts. Run `make help`.
SHELL := /bin/bash
INDEXER := cd indexer && uv run
DASHBOARD := cd dashboard &&
DOCS_VENV := .venv-docs
MKDOCS := NO_MKDOCS_2_WARNING=1 $(DOCS_VENV)/bin/mkdocs

.PHONY: help setup db migrate verify backfill run export-dune export-static test lint dashboard \
	docs docs-serve demo-video ci

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup: ## Install indexer and dashboard dependencies
	cd indexer && uv sync
	$(DASHBOARD) npm ci

db: ## Start a local Postgres (docker compose)
	docker compose up -d db

migrate: ## Apply SQL migrations
	$(INDEXER) loop-indexer db migrate

verify: ## Check the contract registry against the chain
	$(INDEXER) loop-indexer registry verify

backfill: ## Fast daily backfill (good for a first look)
	$(INDEXER) loop-indexer run --interval 1d

run: ## Hourly indexing (fills every missing hour since deployment)
	$(INDEXER) loop-indexer run

export-dune: ## Append new rows to Dune
	$(INDEXER) loop-indexer export dune

export-static: ## Refresh the dashboard's static snapshot
	$(INDEXER) loop-indexer export static --out ../dashboard/data

test: ## Run all tests (set TEST_DATABASE_URL for the Postgres suite)
	$(INDEXER) pytest
	$(DASHBOARD) npm test

lint: ## Lint and type-check everything
	$(INDEXER) ruff check src tests
	$(INDEXER) ruff format --check src tests
	$(INDEXER) mypy
	$(DASHBOARD) npm run typecheck

dashboard: ## Run the dashboard locally
	$(DASHBOARD) npm run dev

$(DOCS_VENV): docs/requirements.txt
	python3 -m venv $(DOCS_VENV) && $(DOCS_VENV)/bin/pip install -q -r docs/requirements.txt
	touch $(DOCS_VENV)

docs: $(DOCS_VENV) ## Build the documentation site (strict, like CI) into site/
	$(MKDOCS) build --strict

docs-serve: $(DOCS_VENV) ## Serve the documentation site with live reload
	$(MKDOCS) serve

demo-video: ## Re-record docs/assets/demo.mp4 (dashboard on DEMO_URL; Playwright + ffmpeg)
	node scripts/record-demo.mjs docs/assets/demo.mp4

ci: lint test ## What CI runs
