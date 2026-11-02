# syntax=docker/dockerfile:1.7
# Build context: repository root (the image also ships supabase/migrations).
#   docker build -f indexer/Dockerfile -t loop-indexer .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY indexer/pyproject.toml indexer/uv.lock indexer/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY indexer/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 indexer
WORKDIR /app
COPY --from=build --chown=indexer:indexer /app/.venv /app/.venv
COPY --chown=indexer:indexer supabase/migrations /app/migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    MIGRATIONS_DIR=/app/migrations \
    LOG_FORMAT=json \
    PYTHONUNBUFFERED=1
USER indexer
ENTRYPOINT ["loop-indexer"]
CMD ["--help"]
