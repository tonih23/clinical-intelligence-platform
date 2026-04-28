# Clinical Intelligence Platform (CIP)

Plataforma end-to-end para ingestar literatura biomédica (PubMed) y ensayos clínicos (ClinicalTrials.gov), procesarlos, indexarlos y servirlos a través de un agente conversacional con RAG.

Este repositorio se construye en sprints incrementales. Cada sprint añade una capa.

## Estado actual

**Sprint 1 — MVP funcional sin AI** (este código).

Lo que hace ahora mismo:

1. Descarga metadata de papers de PubMed vía la API E-utilities del NCBI.
2. Persiste los papers en Postgres.
3. Guarda el XML crudo de cada paper en object storage (MinIO, compatible con S3).
4. Expone una API HTTP con FastAPI: listar papers, obtener uno por PMID, buscar por palabra clave.
5. Todo levanta con `docker compose up`.

## Arquitectura objetivo (final, no Sprint 1)

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────────┐
│ PubMed API      │      │ ClinicalTrials   │      │ Otros sources      │
└────────┬────────┘      └────────┬─────────┘      └──────────┬─────────┘
         │                        │                            │
         ▼                        ▼                            ▼
              ┌──────────────────────────────────┐
              │ Airflow (orquestación)           │
              └────────────────┬─────────────────┘
                               │
              ┌────────────────┴──────────────────┐
              ▼                                    ▼
    ┌──────────────────┐                 ┌──────────────────┐
    │ Postgres (OLTP)  │                 │ Snowflake (OLAP) │
    └──────────┬───────┘                 └──────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Elasticsearch        │ ◄── BM25 + dense vectors
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Agent (Google ADK)   │
    │   + RAG + tools      │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ FastAPI / MCP server │
    └──────────────────────┘
```

## Quickstart (Sprint 1)

Requisitos:

- Docker Desktop con Docker Compose v2
- Python 3.12 (solo si quieres correr cosas fuera de Docker)

Pasos:

```bash
# 1. Clona el repo (cuando lo subas a GitHub)
git clone https://github.com/<tu-usuario>/clinical-intelligence-platform.git
cd clinical-intelligence-platform

# 2. Copia el .env de ejemplo
cp .env.example .env

# 3. Levanta toda la infra (postgres + minio + api)
docker compose up -d --build

# 4. Espera ~10 segundos a que Postgres esté listo, luego inicializa el esquema
docker compose exec api python -m cip.db_init

# 5. Lanza la ingesta (descarga 100 papers sobre "complement system" — relevante para Alexion)
docker compose exec api python -m cip.ingest --query "complement system" --max-results 100

# 6. Comprueba la API
curl http://localhost:8000/health
curl http://localhost:8000/papers?limit=5
curl http://localhost:8000/papers/search?q=complement
```

Interfaces web:

- API docs (Swagger): http://localhost:8000/docs
- MinIO console: http://localhost:9001 (user: `minioadmin`, pass: `minioadmin`)

## Estructura del repo

```
clinical-intelligence-platform/
├── src/cip/                  # Código de la aplicación
│   ├── config.py             # Settings (pydantic-settings)
│   ├── db.py                 # SQLAlchemy: engine, sesión, modelos ORM
│   ├── db_init.py            # Crea las tablas
│   ├── storage.py            # Cliente S3/MinIO (boto3)
│   ├── pubmed.py             # Cliente PubMed E-utilities
│   ├── ingest.py             # Pipeline de ingesta (CLI)
│   └── api.py                # FastAPI: endpoints HTTP
├── scripts/                  # Scripts auxiliares (SQL, etc.)
├── tests/                    # Tests con pytest
├── docs/                     # Documentación adicional
├── docker-compose.yml        # Orquestación local
├── Dockerfile                # Imagen del servicio API
├── pyproject.toml            # Dependencias y metadatos del proyecto
├── .env.example              # Variables de entorno de ejemplo
├── .gitignore
└── README.md
```

## Decisiones técnicas (Sprint 1)

| Necesidad | Elegido | Por qué | Alternativas |
|-----------|---------|---------|--------------|
| Lenguaje | Python 3.12 | Estándar en AI engineering | Go, Rust para servicios de muy alto rendimiento |
| Gestor de paquetes | `uv` | Rápido, moderno, lo que se está imponiendo | `pip`, `poetry`, `pdm` |
| Web framework | FastAPI | Async, OpenAPI nativo, lo más usado en AI/Python | Flask, Django, Litestar |
| ORM | SQLAlchemy 2.0 (async) | Estándar en Python | Tortoise, Pony, SQLModel |
| Validación | Pydantic v2 | Estándar moderno, integrado con FastAPI | attrs, marshmallow |
| DB operacional | Postgres 16 | El rey de OLTP en empresas modernas | MySQL, MariaDB |
| Object storage | MinIO (compatible S3) | Local sin pagar AWS, mismo SDK | Ceph, GCS local emulator |
| Cliente S3 | boto3 | Estándar AWS, funciona con MinIO | aioboto3 (async), minio-py |
| HTTP client | httpx | Async, sustituto moderno de requests | aiohttp, requests (sync) |
| Logging | structlog | Logs estructurados (JSON) | logging stdlib |
| Tests | pytest + pytest-asyncio | Estándar absoluto | unittest |

## Roadmap

Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## Licencia

MIT.
