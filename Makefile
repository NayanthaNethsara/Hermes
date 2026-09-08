# The Archivist Makefile

.DEFAULT_GOAL := help

VENV := src/backend/.venv
PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(if $(wildcard .venv/bin/python),.venv/bin/python,python3))
UVICORN := $(if $(wildcard $(VENV)/bin/uvicorn),$(VENV)/bin/uvicorn,$(if $(wildcard .venv/bin/uvicorn),.venv/bin/uvicorn,uvicorn))
NPM := npm

HOST ?= 127.0.0.1
PORT ?= 8000
Q ?= In which year was the 'Gauntlet of Sorrowfell' actually forged?

.PHONY: help setup setup-backend setup-frontend backend frontend health ask clean docker-build docker-up docker-down docker-logs export-chat

help:
	@echo "The Archivist - Command Reference"
	@echo ""
	@echo "Setup:"
	@echo "  make setup            Install backend (src/backend) and frontend dependencies"
	@echo "  make setup-backend    Install backend package and dependencies using uv or venv"
	@echo "  make setup-frontend   Install frontend node_modules"
	@echo ""
	@echo "Services:"
	@echo "  make db               Start PostgreSQL + pgvector container"
	@echo "  make db-down          Stop PostgreSQL container"
	@echo "  make backend          Start FastAPI backend server (port $(PORT))"
	@echo "  make frontend         Start Next.js frontend dev server"
	@echo ""
	@echo "Ingestion:"
	@echo "  make ingest           Run offline ingestion on entire raw archive"
	@echo "  make ingest-images    Ingest figure plates and visual assets only"
	@echo "  make ingest-wiki      Ingest wiki articles and associated diagrams"
	@echo ""
	@echo "Testing & Query:"
	@echo "  make health           Check backend health endpoint"
	@echo "  make ask              Run orchestrator CLI with question (override with Q=\"...\")"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker images for backend and frontend"
	@echo "  make docker-up        Start all services in detached mode"
	@echo "  make docker-down      Stop and remove containers"
	@echo "  make docker-logs      Follow container logs"
	@echo ""
	@echo "  make clean            Remove build caches and temporary files"
	@echo "  make export-chat      Export current AI chat session to ai_usage/"

export-chat:
	python3 ai_usage/export_chat.py

setup-backend:
	@if command -v uv >/dev/null 2>&1; then \
		echo "Syncing dependencies with uv from src/backend/pyproject.toml..."; \
		uv sync --project src/backend; \
	else \
		if [ ! -d "$(VENV)" ]; then \
			echo "Creating virtual environment in $(VENV)..."; \
			python3 -m venv $(VENV); \
		fi; \
		$(VENV)/bin/pip install --upgrade pip; \
		$(VENV)/bin/pip install -e src/backend; \
	fi

setup-frontend:
	$(NPM) --prefix src/frontend install

setup: setup-backend setup-frontend

db:
	docker compose up -d db

db-down:
	docker compose stop db

db-clean:
	docker compose down -v
	docker compose up -d db

backend:
	$(UVICORN) src.backend.main:app --reload --host $(HOST) --port $(PORT)

ingest:
	$(PYTHON) -m src.backend.workers.run_ingest

preprocess-visuals:
	$(PYTHON) scripts/preprocess_visuals.py

ingest-images:
	$(PYTHON) -m src.backend.workers.run_ingest --folder images

ingest-wiki:
	$(PYTHON) -m src.backend.workers.run_ingest --folder wiki

frontend:
	$(NPM) --prefix src/frontend run dev

health:
	curl -i http://$(HOST):$(PORT)/api/health

ask:
	$(PYTHON) -c 'import asyncio; from src.backend.agents.graphs.multimodal_1a import build_multimodal_1a_graph; from src.backend.agents.state.base import create_initial_state; g = build_multimodal_1a_graph(); res = asyncio.run(g.ainvoke(create_initial_state("$(Q)"))); print("\n--- ANSWER ---\n" + res.get("final_answer", "") + "\n\n--- FIGURES ---\n" + str(res.get("referenced_figures", [])))'

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[cod]" -delete
	rm -rf .pytest_cache .ruff_cache
