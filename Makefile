# The Archivist Makefile

.DEFAULT_GOAL := help

VENV := .venv
PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
UVICORN := $(if $(wildcard $(VENV)/bin/uvicorn),$(VENV)/bin/uvicorn,uvicorn)
PIP := $(if $(wildcard $(VENV)/bin/pip),$(VENV)/bin/pip,pip)
NPM := npm

HOST ?= 127.0.0.1
PORT ?= 8000
CORPUS_PATH ?= ./corpus
QUESTIONS_PATH ?= sample_questions_1b_1c.json
Q ?= In which year was the 'Gauntlet of Sorrowfell' actually forged?

.PHONY: help setup setup-venv setup-frontend backend frontend bot ingest build-graph health eval ask clean

help:
	@echo "The Archivist - Command Reference"
	@echo ""
	@echo "Setup:"
	@echo "  make setup            Install both Python backend and Node frontend dependencies"
	@echo "  make setup-venv       Create local .venv and install requirements.txt"
	@echo "  make setup-frontend   Install frontend node_modules"
	@echo ""
	@echo "Services:"
	@echo "  make backend          Start FastAPI backend server (port $(PORT))"
	@echo "  make frontend         Start Next.js frontend dev server"
	@echo "  make bot              Run Telegram bot (long-polling)"
	@echo ""
	@echo "Data Pipeline:"
	@echo "  make ingest           Ingest corpus into Chroma DB (override with CORPUS_PATH=...)"
	@echo "  make build-graph      Extract entities/relations and build knowledge graph"
	@echo ""
	@echo "Testing & Evaluation:"
	@echo "  make health           Check backend health endpoint"
	@echo "  make eval             Run evaluation harness over $(QUESTIONS_PATH)"
	@echo "  make ask              Run orchestrator CLI with question (override with Q=\"...\")"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            Remove build caches and temporary files"

setup-venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment in $(VENV)..."; \
		python3 -m venv $(VENV); \
	fi
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

setup-frontend:
	$(NPM) --prefix src/frontend install

setup: setup-venv setup-frontend

backend:
	$(UVICORN) src.backend.main:app --reload --host $(HOST) --port $(PORT)

frontend:
	$(NPM) --prefix src/frontend run dev

bot:
	$(PYTHON) -m src.bot.telegram_bot

ingest:
	$(PYTHON) -m src.ingestion.ingest --corpus-path $(CORPUS_PATH)

build-graph:
	$(PYTHON) -m src.ingestion.build_graph

health:
	curl -i http://$(HOST):$(PORT)/api/health

eval:
	$(PYTHON) -m src.eval.run_eval --questions-path $(QUESTIONS_PATH)

ask:
	$(PYTHON) -m src.backend.orchestrator "$(Q)"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[cod]" -delete
	rm -rf .pytest_cache
