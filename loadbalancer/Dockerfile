# Task 2/3: load balancer image
FROM python:3.12-slim

# Docker CLI — the load balancer spawns/removes server containers through the
# host's docker daemon (socket is mounted in docker-compose.yml).
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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

CMD ["uv", "run", "uvicorn", "loadbalancer:app", "--host", "0.0.0.0", "--port", "5000"]
