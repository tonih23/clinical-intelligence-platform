# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project Goal

Clinical Intelligence Platform for AI Engineering and MLOps learning.

Build the platform incrementally as a practical learning project: each sprint adds one working layer to an end-to-end clinical literature, data, retrieval, agent, and MLOps system.

## Working Rules

- Work one sprint at a time.
- Do not advance to a new layer until the current layer works and has tests.
- Before major changes, inspect `README.md`, `docs/SETUP.md`, and `docs/ROADMAP.md`.
- Every feature must include tests, or a written reason why tests are not practical for that change.
- Run `ruff`, `mypy`, and `pytest` before the final answer.
- Prefer local and free tools first. Paid cloud services must have a local fallback.

## Secrets And Environment

- Never commit secrets.
- Never edit `.env`.
- Use `.env.example` only for documenting environment variables.
- If a secret is needed for local use, tell the human what variable is required and where it should be set.

## Current Stack

- Python 3.12
- FastAPI
- SQLAlchemy async
- Postgres
- MinIO
- Docker Compose
- pytest
- ruff
- mypy

## Current Direction

Current completed layer: Sprint 1 MVP with PubMed ingestion, Postgres, MinIO, FastAPI, Docker Compose, and tests.

Next sprint target: Airflow + DuckDB/dbt + Great Expectations. Snowflake is optional later, not required for the local-first path.

## Quality Bar

- Keep changes small, practical, and aligned with the roadmap.
- Prefer existing repo patterns over new abstractions.
- Update docs when behavior, commands, setup, or architecture changes.
- Keep local development runnable without paid services.
- Do not leave broken tests or type/lint failures unexplained.
