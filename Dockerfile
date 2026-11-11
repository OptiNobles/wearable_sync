# syntax=docker/dockerfile:1

# --- Build stage: install dependencies and the package into a virtualenv ---
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first: this layer is reused as long as the lock file is unchanged.
# --locked fails the build if uv.lock is out of date with pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Then the project itself, installed as a regular (non-editable) package,
# so the runtime stage needs only the virtualenv, not the source tree.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Runtime stage: only Python and the virtualenv ---
FROM python:3.13-slim

RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# SINK=databricks: the container filesystem is ephemeral (and /app is not
# writable for the app user), so the image only supports the Databricks sink.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SINK=databricks

USER app

# Configuration and secrets come from environment variables at runtime.
ENTRYPOINT ["wearable-sync"]
