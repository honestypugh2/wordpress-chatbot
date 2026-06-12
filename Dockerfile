# syntax=docker/dockerfile:1.7
# =============================================================================
# County Assistant backend — multi-stage build with uv.
#
# Build & push (matches infra/main.bicep `backendImage`):
#   az acr build -r <registry> -t county-assistant:latest .
#   # or:
#   docker build -t <registry>.azurecr.io/county-assistant:latest .
#   docker push <registry>.azurecr.io/county-assistant:latest
#
# Then deploy with deployBackend=true:
#   az deployment group create -g <rg> -f infra/main.bicep \
#     -p infra/main.bicepparam -p deployBackend=true \
#     -p backendImage=<registry>.azurecr.io/county-assistant:latest
#
# NOTE: pyproject pins azure-ai-projects/agent-framework to the requested
# prototype targets — verify those versions resolve before a production build.
# =============================================================================

# ---- Builder: resolve and install dependencies into a venv ------------------
FROM ghcr.io/astral-sh/uv:0.11-python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Project metadata + sources are needed because the hatchling build backend
# packages src/app. Copy them before sync so the layer caches on dependency
# changes.
COPY pyproject.toml README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --extra rag

# ---- Runtime: minimal image with the prebuilt venv --------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=prod \
    APP_LOG_JSON=true \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

# Run as a non-root user.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Virtual environment and application code.
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
# Synthetic knowledge base for the local-fallback retriever (used when Azure AI
# Search is not configured).
COPY data ./data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
