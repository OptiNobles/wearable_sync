# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e

# Images (and the BuildKit frontend above) are pinned by digest, tag kept for
# readability, so every build uses exactly the same toolchain. Dependabot opens a
# pull request when a FROM image changes; it does not read 'COPY --from=<image>',
# hence the separate uv stage.

# uv binary only. Its version must match [tool.uv] required-version in pyproject.toml,
# which CI also uses, or 'uv sync' below fails - so the two cannot drift apart.
FROM ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 AS uv

# --- Build stage: install dependencies and the package into a virtualenv ---
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS builder

COPY --from=uv /uv /bin/uv

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
# Same digest as the builder: the virtualenv must run on the interpreter it was built with.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

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
