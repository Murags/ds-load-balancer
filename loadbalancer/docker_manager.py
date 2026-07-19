"""Thin async wrapper around the docker CLI.

The load balancer container has the docker CLI installed and the host's docker
socket mounted, so it drives the host daemon to spawn/remove server replicas.
All spawned replicas carry the label ``role=ds-lb-server`` so they can be
discovered (after a restart) and cleaned up.
"""
from __future__ import annotations

import asyncio

SERVER_LABEL = "role=ds-lb-server"
SERVER_PORT = 5000


class DockerError(RuntimeError):
    """A docker CLI command exited non-zero."""


async def _run(*args: str) -> tuple[int, str, str]:
    """Run a docker command, returning (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode().strip(), err.decode().strip()


async def spawn_server(hostname: str, image: str, network: str) -> str:
    """Start a detached server container on `network` and return its id.

    The container is named/aliased `hostname` (so other containers resolve it
    via docker DNS) and gets SERVER_ID=<hostname> so its /home response is
    traceable back to the replica.
    """
    code, out, err = await _run(
        "run",
        "-d",
        "--name", hostname,
        "--network", network,
        "--network-alias", hostname,  # lets other containers resolve this replica by name via docker DNS
        "--label", SERVER_LABEL,
        "-e", f"SERVER_ID={hostname}",
        image,
    )
    if code != 0:
        raise DockerError(f"failed to spawn {hostname!r}: {err or out}")
    return out


async def remove_server(hostname: str) -> None:
    """Force-remove a server container. Missing containers are ignored."""
    code, _out, err = await _run("rm", "-f", hostname)
    if code != 0 and "No such container" not in err:  # "already gone" isn't a real failure
        raise DockerError(f"failed to remove {hostname!r}: {err}")


async def list_servers() -> list[str]:
    """Names of all running replicas tagged with the server label."""
    code, out, err = await _run(
        "ps", "--filter", f"label={SERVER_LABEL}", "--format", "{{.Names}}"
    )
    if code != 0:
        raise DockerError(f"failed to list servers: {err}")
    return [name for name in out.splitlines() if name]  # drop trailing empty line when there are no matches