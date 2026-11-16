# Atajos del proyecto. Requiere uv (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help
PY := uv run --no-sync python

help: ## Lista los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Crea el entorno con todas las dependencias y los hooks de pre-commit
	uv sync --all-groups
	uv run pre-commit install

data: ## Descarga PaySim desde Kaggle (requiere ~/.kaggle/kaggle.json)
	bash scripts/download_data.sh

pipeline: ## CSV -> bronce -> plata -> oro -> modelos, métricas y datos de demo
	$(PY) -m fraud_p2p.pipeline all

train: ## Reentrena desde la capa oro existente
	$(PY) -m fraud_p2p.pipeline train

test: ## Corre los tests
	uv run --no-sync pytest

lint: ## Revisa estilo y errores comunes
	uv run --no-sync ruff check .
	uv run --no-sync ruff format --check src api app replayer tests

api: ## Levanta la API en local (SQLite)
	uv run --no-sync uvicorn api.main:app --reload --port 8000

app: ## Levanta la aplicación web en local
	uv run --no-sync streamlit run app/streamlit_app.py

replay: ## Reproduce el tráfico de demostración contra la API local
	$(PY) -m replayer.replay --api http://localhost:8000 --seconds-per-hour 0.5

up: ## Levanta la plataforma completa con Docker
	docker compose up --build -d
	@echo "API: http://localhost:8000/docs · Aplicación: http://localhost:8501"

down: ## Detiene la plataforma y borra los datos operativos
	docker compose down -v

logs: ## Sigue los logs de los contenedores
	docker compose logs -f --tail=50

.PHONY: help setup data pipeline train test lint api app replay up down logs
