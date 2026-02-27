FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# System deps (build tools + Postgres client libs for asyncpg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv (project uses pyproject.toml + uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency metadata first for better Docker layer caching
COPY pyproject.toml uv.lock ./

# Create virtualenv and install dependencies (locked)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy the rest of the application code
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Expose default FastAPI port
EXPOSE 8002

ENV UVICORN_PORT=8002

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
