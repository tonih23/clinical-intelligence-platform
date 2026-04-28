# ============================================================
# Stage 1: builder — instala dependencias con uv
# ============================================================
FROM python:3.12-slim AS builder

# Instala uv (gestor de paquetes rápido)
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Copia primero los archivos de dependencias para aprovechar la caché
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

# Crea el entorno e instala dependencias.
# TODO: separar imágenes dev/prod cuando el proyecto deje de ser un portfolio de aprendizaje.
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python -e ".[dev]"

# ============================================================
# Stage 2: runtime — imagen final delgada
# ============================================================
FROM python:3.12-slim AS runtime

# Dependencias del sistema (curl para healthchecks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Usuario no-root (mejor práctica de seguridad)
RUN useradd --create-home --shell /bin/bash cip
USER cip

WORKDIR /app

# Copia el entorno virtual ya construido y el código
COPY --from=builder --chown=cip:cip /opt/venv /opt/venv
COPY --chown=cip:cip src/ ./src/
COPY --chown=cip:cip tests/ ./tests/
COPY --chown=cip:cip pyproject.toml ./
COPY --chown=cip:cip README.md ./

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "cip.api:app", "--host", "0.0.0.0", "--port", "8000"]
