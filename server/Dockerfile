# Task 1: server image
FROM python:3.12-slim

# uv binary (pinned to match the version that generated uv.lock)
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application code.
COPY . .

EXPOSE 5000

# SERVER_ID is injected per-container by the load balancer at spawn time.
CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5000"]
