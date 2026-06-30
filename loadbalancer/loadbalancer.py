"""Task 3: load balancer.

Routes client requests across N server replicas using the Task 2 consistent
hash ring, exposes management endpoints (/rep, /add, /rm), proxies GET /<path>
to a replica, and maintains N healthy replicas by polling /heartbeat and
respawning any that die.

Configuration (env, with defaults):
    N                  number of replicas to maintain        (3)
    SERVER_IMAGE       image used for spawned replicas        (ds-server:latest)
    DOCKER_NETWORK     network replicas join                  (net1)
    HEARTBEAT_INTERVAL seconds between health sweeps          (5)
"""
from __future__ import annotations

import asyncio
import os
import random
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

import docker_manager as dm
from docker_manager import SERVER_PORT
from hashing import ConsistentHashMap

N = int(os.environ.get("N", "3"))
SERVER_IMAGE = os.environ.get("SERVER_IMAGE", "ds-server:latest")
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "net1")
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5"))
READINESS_TIMEOUT = float(os.environ.get("READINESS_TIMEOUT", "20"))

# Shared state. `_lock` guards every mutation of the ring + docker topology so
# the /add, /rm endpoints and the health loop never race each other.
ring = ConsistentHashMap()
# Desired replica count to maintain on failure. Starts at N, then tracks the
# live count as /add and /rm scale the pool up and down.
_target_n = N
_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None
_health_task: asyncio.Task | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _random_hostname() -> str:
    return "server_" + uuid.uuid4().hex[:8]


def _ok(replicas: list[str], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "message": {"N": len(replicas), "replicas": replicas},
            "status": "successful",
        },
    )


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"message": f"<Error> {message}", "status": "failure"},
    )


async def _is_alive(hostname: str, attempts: int = 2) -> bool:
    """Poll a replica's /heartbeat; alive if any attempt returns 200."""
    assert _client is not None
    for _ in range(attempts):
        try:
            r = await _client.get(
                f"http://{hostname}:{SERVER_PORT}/heartbeat", timeout=2.0
            )
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
    return False


async def _wait_healthy(hostname: str) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + READINESS_TIMEOUT
    while loop.time() < deadline:
        if await _is_alive(hostname, attempts=1):
            return True
        await asyncio.sleep(0.5)
    return False


async def _spawn_and_register(hostname: str, wait: bool = True) -> None:
    """Spawn a replica, register it on the ring, optionally await readiness."""
    await dm.spawn_server(hostname, SERVER_IMAGE, DOCKER_NETWORK)
    ring.add_server(hostname)
    if wait:
        await _wait_healthy(hostname)


async def _ensure_n_replicas() -> None:
    """Spawn replicas until the ring holds N of them (used at startup)."""
    idx = 1
    while len(ring) < N:
        name = f"server{idx}"
        idx += 1
        if name in ring:
            continue
        await _spawn_and_register(name)


# --------------------------------------------------------------------------- #
# Health / failure recovery
# --------------------------------------------------------------------------- #
async def _recover_dead() -> None:
    """Detect dead replicas and respawn replacements to keep N alive."""
    dead = [name for name in ring.servers if not await _is_alive(name)]
    if not dead:
        return
    async with _lock:
        for name in dead:
            if name in ring:
                ring.remove_server(name)
            try:
                await dm.remove_server(name)
            except dm.DockerError:
                pass
        # Top back up to the desired count with fresh, randomly-named replicas.
        while len(ring) < _target_n:
            replacement = _random_hostname()
            if replacement in ring:
                continue
            try:
                await _spawn_and_register(replacement)
            except dm.DockerError:
                break


async def _health_loop() -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await _recover_dead()
        except asyncio.CancelledError:
            raise
        except Exception:  # never let the loop die on a transient error
            pass


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _health_task, _target_n
    _client = httpx.AsyncClient()
    async with _lock:
        # Adopt any replicas left over from a previous run, then top up to N.
        for name in await dm.list_servers():
            if name not in ring:
                ring.add_server(name)
        await _ensure_n_replicas()
        _target_n = len(ring)  # keep adopted extras; never trim healthy replicas
    _health_task = asyncio.create_task(_health_loop())
    try:
        yield
    finally:
        if _health_task:
            _health_task.cancel()
        await _client.aclose()


app = FastAPI(title="ds-loadbalancer", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Management endpoints
# --------------------------------------------------------------------------- #
@app.get("/rep")
async def rep() -> JSONResponse:
    """Return the count and hostnames of the managed replicas."""
    return _ok(ring.servers)


@app.post("/add")
async def add(request: Request) -> JSONResponse:
    """Add `n` replicas, using preferred hostnames where given."""
    global _target_n
    try:
        payload = await request.json()
    except Exception:
        return _error("invalid JSON payload")

    n = payload.get("n")
    hostnames = payload.get("hostnames", [])
    if not isinstance(n, int) or n <= 0:
        return _error("'n' must be a positive integer")
    if not isinstance(hostnames, list):
        return _error("'hostnames' must be a list")
    if len(hostnames) > n:
        return _error("Length of hostname list is more than newly added instances")
    if len(set(hostnames)) != len(hostnames):
        return _error("Duplicate hostnames in payload")

    async with _lock:
        for h in hostnames:
            if h in ring:
                return _error(f"Hostname '{h}' already exists")
        chosen = list(hostnames)
        while len(chosen) < n:
            r = _random_hostname()
            if r not in ring and r not in chosen:
                chosen.append(r)
        for h in chosen:
            await _spawn_and_register(h)
        _target_n = len(ring)
        return _ok(ring.servers)


@app.delete("/rm")
async def remove(request: Request) -> JSONResponse:
    """Remove `n` replicas, honoring preferred hostnames where given."""
    global _target_n
    try:
        payload = await request.json()
    except Exception:
        return _error("invalid JSON payload")

    n = payload.get("n")
    hostnames = payload.get("hostnames", [])
    if not isinstance(n, int) or n <= 0:
        return _error("'n' must be a positive integer")
    if not isinstance(hostnames, list):
        return _error("'hostnames' must be a list")
    if len(hostnames) > n:
        return _error("Length of hostname list is more than removable instances")

    async with _lock:
        if n > len(ring):
            return _error("Cannot remove more instances than are present")
        for h in hostnames:
            if h not in ring:
                return _error(f"Hostname '{h}' is not a managed replica")
        chosen = list(hostnames)
        # Fill the remainder with randomly-chosen survivors.
        others = [s for s in ring.servers if s not in chosen]
        chosen += random.sample(others, n - len(chosen))
        for h in chosen:
            ring.remove_server(h)
            try:
                await dm.remove_server(h)
            except dm.DockerError:
                pass
        _target_n = len(ring)
        return _ok(ring.servers)


# --------------------------------------------------------------------------- #
# Request routing (must be declared last so it doesn't shadow the routes above)
# --------------------------------------------------------------------------- #
@app.get("/{path:path}")
async def route(path: str, request: Request) -> Response:
    """Route a GET request to a replica chosen by the consistent hash ring."""
    assert _client is not None
    if not ring.servers:
        return _error("No server replicas available", status_code=503)

    request_id = random.randint(100000, 999999)
    server = ring.get_server(request_id)
    url = f"http://{server}:{SERVER_PORT}/{path}"
    try:
        resp = await _client.get(url, timeout=10.0)
    except httpx.HTTPError:
        # The chosen replica is unreachable; the health loop will recover it.
        return _error(f"replica '{server}' is unreachable", status_code=502)

    if resp.status_code == 404:
        return _error(f"'/{path}' endpoint does not exist in server replicas")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )
