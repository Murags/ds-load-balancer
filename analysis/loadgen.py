"""Async load generator for the load balancer (Task 4).

Fires a fixed number of concurrent GET /home requests at the load balancer and
buckets the responses by the replica that served them (parsed from the
"Hello from Server: <id>" message).
"""
from __future__ import annotations

import asyncio
from collections import Counter

import httpx


def _parse_server(message: str) -> str | None:
    marker = "Hello from Server:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return None


async def fire_requests(
    base_url: str, total: int, concurrency: int
) -> tuple[Counter, int]:
    """Send `total` GET /home requests, max `concurrency` in flight.

    Returns (counts_by_server, error_count).
    """
    counts: Counter = Counter()
    errors = 0
    sem = asyncio.Semaphore(concurrency)
    # Reuse keep-alive connections so 10k requests don't churn 10k TCP sockets
    # through Docker's port-forwarder (which exhausts ephemeral ports).
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )

    async with httpx.AsyncClient(timeout=10.0, limits=limits) as client:

        async def one() -> None:
            nonlocal errors
            async with sem:
                try:
                    r = await client.get(f"{base_url}/home")
                except httpx.HTTPError:
                    errors += 1
                    return
                if r.status_code != 200:
                    errors += 1
                    return
                server = _parse_server(r.json().get("message", ""))
                if server is None:
                    errors += 1
                else:
                    counts[server] += 1

        await asyncio.gather(*(one() for _ in range(total)))

    return counts, errors


async def _get_replicas_retry(client: httpx.AsyncClient, base_url: str) -> list[str]:
    """GET /rep, retrying transient connection failures (port exhaustion etc.)."""
    last: Exception | None = None
    for attempt in range(10):
        try:
            r = await client.get(f"{base_url}/rep")
            return r.json()["message"]["replicas"]
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"/rep unreachable after retries: {last}")


async def get_replicas(base_url: str) -> list[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await _get_replicas_retry(client, base_url)


async def scale_to(base_url: str, target: int, settle: float = 2.0) -> list[str]:
    """Scale the managed pool to exactly `target` replicas via /add or /rm."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        reps = await _get_replicas_retry(client, base_url)
        diff = target - len(reps)
        if diff > 0:
            await client.post(f"{base_url}/add", json={"n": diff, "hostnames": []})
        elif diff < 0:
            await client.request(
                "DELETE", f"{base_url}/rm", json={"n": -diff, "hostnames": []}
            )
        await asyncio.sleep(settle)  # let new replicas finish booting
        return await _get_replicas_retry(client, base_url)
