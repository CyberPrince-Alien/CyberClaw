FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for playwright and edge-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ src/
COPY workspace/ workspace/
COPY scripts/ scripts/

# Install uv and project
RUN pip install uv && uv sync --no-dev

# Default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); r.raise_for_status()"

# Run the gateway
CMD ["uv", "run", "cyberclaw", "server"]
