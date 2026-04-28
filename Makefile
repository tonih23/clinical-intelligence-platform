# ============================================================
# CIP — Comandos comunes
# ============================================================
# Uso: `make help` para ver todo lo disponible.

.PHONY: help up down logs build init-db ingest test fmt lint shell clean

help:  ## Lista de comandos
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

up:  ## Levanta toda la infra (postgres + minio + api)
	docker compose up -d --build

down:  ## Para los contenedores (mantiene los volúmenes)
	docker compose down

down-clean:  ## Para los contenedores Y borra los volúmenes (cuidado: borra los datos)
	docker compose down -v

logs:  ## Sigue los logs de la API
	docker compose logs -f api

build:  ## Construye la imagen Docker de la API
	docker compose build api

init-db:  ## Crea las tablas en Postgres (correr una sola vez tras `make up`)
	docker compose exec api python -m cip.db_init

ingest:  ## Ingesta papers (override con `make ingest QUERY="..." N=100`)
	docker compose exec api python -m cip.ingest --query "$(QUERY)" --max-results $(N)

test:  ## Ejecuta los tests
	docker compose exec api pytest -v

fmt:  ## Formatea el código con ruff
	docker compose exec api ruff format src tests
	docker compose exec api ruff check --fix src tests

lint:  ## Valida estilo y tipos
	docker compose exec api ruff check src tests
	docker compose exec api mypy src

shell:  ## Abre un shell dentro del contenedor de la API
	docker compose exec api /bin/bash

shell-db:  ## Abre psql contra Postgres
	docker compose exec postgres psql -U cip -d cip

clean:  ## Limpia caches locales
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

# Defaults para `make ingest`
QUERY ?= complement system
N ?= 100
