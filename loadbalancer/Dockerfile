# Task 2/3: load balancer image
FROM python:3.12-slim

# Docker CLI only (no daemon) — the load balancer spawns/removes server
# containers through the host's docker daemon via the mounted socket, so it
# just needs the client binary. Copied from the official docker image.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

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
