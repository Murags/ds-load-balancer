"""Task 1: minimal web server.

A simple HTTP server that the load balancer replicates across N containers.
Each container is given a unique identity via the SERVER_ID environment
variable (injected by the load balancer when it spawns the container), so
clients can tell which replica handled their request.

Endpoints:
    GET /home       -> identifies the responding replica
    GET /heartbeat  -> liveness probe used by the load balancer
"""
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="ds-lb-server")

# Identity of this replica. Set per-container by the load balancer at spawn
# time; defaults to "0" so the server is still runnable standalone.
SERVER_ID = os.environ.get("SERVER_ID", "0")


@app.get("/home")
async def home() -> JSONResponse:
    """Return a unique identifier distinguishing this replica from the others."""
    return JSONResponse(
        status_code=200,
        content={
            "message": f"Hello from Server: {SERVER_ID}",
            "status": "successful",
        },
    )


@app.get("/heartbeat")
async def heartbeat() -> Response:
    """Liveness probe.

    The load balancer polls this endpoint to detect failed replicas. An empty
    body with a 200 status code is a valid, low-overhead heartbeat.
    """
    return Response(status_code=200)
