# The Archivist Makefile

.DEFAULT_GOAL := help

VENV := src/backend/.venv
PYTHON := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(if $(wildcard .venv/bin/python),.venv/bin/python,python3))
UVICORN := $(if $(wildcard $(VENV)/bin/uvicorn),$(VENV)/bin/uvicorn,$(if $(wildcard .venv/bin/uvicorn),.venv/bin/uvicorn,uvicorn))
NPM := npm

HOST ?= 127.0.0.1
PORT ?= 8000
Q ?= In which year was the 'Gauntlet of Sorrowfell' actually forged?

.PHONY: help setup setup-backend setup-frontend backend frontend health ask clean docker-build docker-up docker-down docker-logs

help:
	@echo "The Archivist - Command Reference"
	@echo ""
	@echo "Setup:"
	@echo "  make setup            Install backend (src/backend) and frontend dependencies"
	@echo "  make setup-backend    Install backend package and dependencies using uv or venv"
	@echo "  make setup-frontend   Install frontend node_modules"
	@echo ""
	@echo "Services:"
	@echo "  make backend          Start FastAPI backend server (port $(PORT))"
	@echo "  make frontend         Start Next.js frontend dev server"
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
	@echo "Utilities:"
	@echo "  make clean            Remove build caches and temporary files"

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

backend:
	$(UVICORN) src.backend.main:app --reload --host $(HOST) --port $(PORT)

frontend:
	$(NPM) --prefix src/frontend run dev

health:
	curl -i http://$(HOST):$(PORT)/api/health

ask:
	$(PYTHON) -m src.backend.orchestrator "$(Q)"

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
