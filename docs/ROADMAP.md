# Roadmap

Plan de construcción incremental. Cada sprint añade UNA capa al sistema.
Regla de oro: **no avanzar de capa hasta que la anterior funciona y tiene tests**.

## ✅ Sprint 1 — MVP funcional (este código)

- Pipeline PubMed → Postgres + MinIO.
- API REST con FastAPI: list, get, search, raw-link, ingest-runs.
- Todo dockerizado.
- Tests del parser.

**Decisión clave:** persistimos el XML crudo en S3 además de los campos
parseados en Postgres. Coste de storage ridículo, pero permite reprocesar
si el parser cambia. Esto es estándar en data lakes — la idea de "raw zone".

**Alternativas:** se podría usar Wikipedia API o arXiv en lugar de PubMed,
o MongoDB en lugar de Postgres + S3 (todo JSON). Postgres + S3 es más
profesional y es lo que usan empresas reales.

---

## Sprint 2 — Data warehouse y orquestación

**Objetivo:** mover de "script que corro a mano" a "pipeline orquestado nocturno".

**Qué construir:**

1. **Apache Airflow** local con docker-compose (LocalExecutor).
2. DAG que ejecute la ingesta cada noche con varias queries paralelas.
3. **Snowflake** como warehouse. Plan gratis: 30 días + $400 de crédito.
   Si no quieres pagar tras 30 días, **DuckDB** local es la alternativa
   gratis (SQL serio, no es Postgres).
4. **dbt-core** (gratis) para transformar `raw → staging → marts`.
5. **Great Expectations** para validar los datos antes de cargar a marts.

**Alternativas a anotar:**

- Airflow ↔ Dagster (más moderno, mejor DX), Prefect (más simple).
- Snowflake ↔ BigQuery (lo más probable que use Alexion), Databricks, DuckDB.
- dbt ↔ SQL puro, dataform.

---

## Sprint 3 — RAG end-to-end

**Objetivo:** búsqueda semántica + léxica sobre los papers.

**Qué construir:**

1. **Elasticsearch 8.x** local (versión OSS) — soporta BM25 + dense vectors nativos.
2. Indexar los papers con embeddings (`gemini-embedding-001` o
   `sentence-transformers/all-mpnet-base-v2` si quieres todo gratis).
3. Hybrid retrieval con **RRF (Reciprocal Rank Fusion)**.
4. Endpoint `/rag/search` que devuelva chunks rankeados.
5. **RAGAS** para evaluar contra un golden set de 30 queries etiquetadas.

**Alternativas:** Pinecone (caro), Qdrant, Weaviate, pgvector. Elastic es
lo que usa el equipo de Anastasiia, mantenlo.

---

## Sprint 4 — Agente conversacional

**Objetivo:** un agente con tools que responde a investigadores.

**Qué construir:**

1. **Google ADK** como framework principal (gratis, lo que usa Anastasiia).
2. 4-5 tools: `search_papers`, `get_paper`, `list_recent_in_journal`,
   `summarize_for_role`, `find_clinical_trials`.
3. Sessions persistidas en Postgres.
4. Integración con `ClinicalTrials.gov` API (gratis, sin key).
5. UI mínima en **Streamlit** (gratis).

**Alternativas:** LangGraph, CrewAI, AutoGen, Haystack, framework propio.

---

## Sprint 5 — Observability

**Objetivo:** ver qué pasa dentro del sistema.

**Qué construir:**

1. **Langfuse** self-hosted (open source, gratis).
2. **MLflow** local para tracking de prompts/modelos.
3. **Prometheus + Grafana** para métricas de la API.
4. CI con **GitHub Actions** que corra tests + evals en cada PR.

**Alternativas:** LangSmith, Phoenix Arize, W&B Weave, Datadog.

---

## Sprint 6 — Deploy a cloud

**Objetivo:** correr en cloud real, no en tu portátil.

**Qué construir:**

1. **GCP** como cloud (Free Tier + $300 crédito inicial). Si lo agotas,
   migra a **Fly.io** (gratis hasta cierto uso) o **Railway**.
2. **Cloud Run** para la API (servidor sin gestión).
3. **Cloud SQL** para Postgres.
4. **GCS** en lugar de MinIO.
5. **Vertex AI** para los LLMs.
6. **Terraform** para todo.

**Alternativas:** AWS (ECS, Fargate), Azure, Hetzner (VPS barato),
Kubernetes con `kind` local sin pagar nada.

---

## Sprint 7 — Multi-agent y patterns avanzados

**Objetivo:** del mono-agente a un sistema con coordinador + sub-agentes.

**Qué construir:**

1. Refactor a multi-agent: `coordinator → search_agent + analysis_agent + writer_agent`.
2. **LangGraph** como segundo framework para comparar (en una rama o sub-proyecto).
3. **Cohere Rerank** (free tier 1000 req/mes) o **BGE-reranker** local.
4. A/B testing de prompts.

---

## Sprint 8 — MLOps avanzado

**Objetivo:** drift detection, cost monitoring, cache.

**Qué construir:**

1. Drift detection: detectar si el retrieval se degrada con el tiempo
   (Evidently AI o lógica propia).
2. Cost tracker: contabiliza tokens de LLM por endpoint.
3. **Redis** como cache de queries calientes.
4. Rate limiting en la API.

---

## Sprint 9 — Polish + MCP layer

**Objetivo:** documentar y exponer las tools como MCP server.

**Qué construir:**

1. **MkDocs** con tema Material para docs.
2. 5-10 blog posts en Medium / dev.to explicando decisiones.
3. **MCP server** que expone las tools del agente a clientes externos
   (Claude Desktop, Cursor, etc.). Esto te conecta directamente con el
   trabajo de Vinod en Alexion.

---

## Mini-experimentos laterales

Carpetas independientes en `experiments/`:

- `exp01-no-framework-agent/` — agente en 100 líneas, sin ADK.
- `exp02-ollama-llama3/` — llama3 self-hosted con Ollama.
- `exp03-bm25-from-scratch/` — implementar BM25 a mano.
- `exp04-vector-db-bench/` — benchmark Elastic vs Qdrant vs pgvector.
- `exp05-fine-tune-tiny/` — fine-tune de un modelo pequeño con HF.

Cada uno te lleva 1-3 días y enseña una pieza fundamental.
