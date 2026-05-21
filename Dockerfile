# Multi-stage build for lightweight final image
FROM ghcr.io/astral-sh/uv:python3.11-alpine AS builder

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies first (caching layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy source code and sync project
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Final runtime image
FROM python:3.11-alpine

WORKDIR /app

# Copy python virtual environment and files
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/workspace /app/workspace
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose API gateway port
EXPOSE 8000

# Mount local workspace directory at runtime
VOLUME ["/app/workspace"]

# Default entrypoint starts the background orchestrator server
CMD ["cyberclaw", "server"]
