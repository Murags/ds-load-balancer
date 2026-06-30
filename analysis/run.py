"""Task 4 analysis orchestrator.

Drives the full load balancer stack through the four required experiments and
writes charts (analysis/figures/) and a summary (analysis/results/summary.json).

  A-1  10,000 requests at N=3, per-server bar chart
  A-2  10,000 requests for N = 2..6, average-load line chart
  A-3  kill a replica, measure how fast the LB respawns it
  A-4  repeat A-1/A-2 with the "spread" hash variant and compare

Run from the analysis project (it shells out to docker compose at the repo root):
    cd analysis && uv run python run.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import charts
import httpx
import loadgen

REPO = Path(__file__).resolve().parent.parent
FIG = Path(__file__).resolve().parent / "figures"
RES = Path(__file__).resolve().parent / "results"
LB_PORT = os.environ.get("LB_PORT", "5050")
BASE = f"http://127.0.0.1:{LB_PORT}"
REQUESTS = int(os.environ.get("REQUESTS", "10000"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "100"))
N_RANGE = [2, 3, 4, 5, 6]


# --------------------------------------------------------------------------- #
# Stack control
# --------------------------------------------------------------------------- #
def _compose(*args: str, variant: str = "default") -> None:
    env = {**os.environ, "LB_PORT": LB_PORT, "HASH_VARIANT": variant}
    subprocess.run(["docker", "compose", *args], cwd=REPO, env=env, check=True)


def build_images() -> None:
    print("· building images …")
    subprocess.run(
        ["docker", "build", "-t", "ds-server:latest", "./server"],
        cwd=REPO, check=True, stdout=subprocess.DEVNULL,
    )
    _compose("build")


def reset_stack(variant: str) -> None:
    print(f"· (re)deploying stack [hash variant: {variant}] …")
    subprocess.run(["make", "down"], cwd=REPO, check=False, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    _compose("up", "-d", variant=variant)
    _wait_healthy()


def _wait_healthy(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{BASE}/rep", timeout=3.0)
            if r.status_code == 200 and r.json()["message"]["N"] >= 1:
                # confirm routing actually works
                if httpx.get(f"{BASE}/home", timeout=3.0).status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise RuntimeError("stack did not become healthy in time")


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def _stats(counts: dict[str, int], n: int) -> dict:
    values = sorted(counts.values(), reverse=True)
    total = sum(values)
    avg = total / n if n else 0
    return {
        "counts": counts,
        "total": total,
        "n": n,
        "avg": avg,
        "max": max(values) if values else 0,
        "min": min(values) if values else 0,
    }


# --------------------------------------------------------------------------- #
# Experiments
# --------------------------------------------------------------------------- #
async def exp_a1(variant: str) -> dict:
    print(f"  A-1: {REQUESTS} requests at N=3 …")
    await loadgen.scale_to(BASE, 3)
    counts, errors = await loadgen.fire_requests(BASE, REQUESTS, CONCURRENCY)
    print(f"       counts={dict(counts)} errors={errors}")
    charts.bar_distribution(
        dict(counts),
        f"A-1: request distribution across N=3 servers ({variant} hashes)",
        str(FIG / f"a1_{variant}.png"),
    )
    return {**_stats(dict(counts), 3), "errors": errors}


async def exp_a2(variant: str) -> dict:
    print(f"  A-2: {REQUESTS} requests for N={N_RANGE} …")
    runs = {}
    for n in N_RANGE:
        await loadgen.scale_to(BASE, n)
        counts, errors = await loadgen.fire_requests(BASE, REQUESTS, CONCURRENCY)
        runs[n] = {**_stats(dict(counts), n), "errors": errors}
        print(f"       N={n}: avg={runs[n]['avg']:.0f} max={runs[n]['max']} "
              f"min={runs[n]['min']} errors={errors}")
    charts.line_loads(
        N_RANGE,
        {
            "average load (total/N)": [runs[n]["avg"] for n in N_RANGE],
            "max server load": [runs[n]["max"] for n in N_RANGE],
            "min server load": [runs[n]["min"] for n in N_RANGE],
        },
        f"A-2: load vs N ({variant} hashes)",
        "Requests per server",
        str(FIG / f"a2_{variant}.png"),
    )
    return runs


async def exp_a3() -> dict:
    print("  A-3: failure recovery …")
    await loadgen.scale_to(BASE, 3)  # clean, spec-aligned N=3
    before = httpx.get(f"{BASE}/rep").json()["message"]["replicas"]
    victim = before[0]
    print(f"       killing {victim} (replicas={before}) …")
    t0 = time.monotonic()
    subprocess.run(["docker", "kill", victim], check=True, stdout=subprocess.DEVNULL)

    recovered_at = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        reps = httpx.get(f"{BASE}/rep").json()["message"]["replicas"]
        if len(reps) >= len(before) and victim not in reps:
            recovered_at = time.monotonic()
            break
        time.sleep(0.5)
    elapsed = (recovered_at - t0) if recovered_at else None
    after = httpx.get(f"{BASE}/rep").json()["message"]["replicas"]
    print(f"       recovered in {elapsed:.1f}s -> replicas={after}"
          if elapsed else "       did NOT recover within 60s")
    return {"killed": victim, "before": before, "after": after,
            "recovery_seconds": elapsed}


# --------------------------------------------------------------------------- #
# A-4 comparison charts
# --------------------------------------------------------------------------- #
def a4_charts(default: dict, spread: dict) -> None:
    # A-1 comparison: per-server counts side by side (N=3).
    d1, s1 = default["a1"]["counts"], spread["a1"]["counts"]
    servers = sorted(set(d1) | set(s1))
    charts.grouped_bar(
        servers,
        {"default": [d1.get(s, 0) for s in servers],
         "spread": [s1.get(s, 0) for s in servers]},
        "A-4: A-1 distribution — default vs spread hashes (N=3)",
        "Requests handled",
        str(FIG / "a4_a1_comparison.png"),
    )
    # A-2 comparison: max server load vs N (lower = better balanced).
    charts.line_loads(
        N_RANGE,
        {"default (max load)": [default["a2"][str(n)]["max"] for n in N_RANGE],
         "spread (max load)": [spread["a2"][str(n)]["max"] for n in N_RANGE],
         "ideal (total/N)": [default["a2"][str(n)]["avg"] for n in N_RANGE]},
        "A-4: most-loaded server vs N — default vs spread hashes",
        "Requests on busiest server",
        str(FIG / "a4_a2_comparison.png"),
    )


def _jsonify(runs: dict) -> dict:
    # JSON keys must be strings (N ints -> str).
    return {str(k): v for k, v in runs.items()}


async def main() -> None:
    FIG.mkdir(exist_ok=True)
    RES.mkdir(exist_ok=True)
    build_images()

    results: dict = {}
    for variant in ("default", "spread"):
        reset_stack(variant)
        a1 = await exp_a1(variant)
        a2 = await exp_a2(variant)
        results[variant] = {"a1": a1, "a2": _jsonify(a2)}
        if variant == "default":
            results["a3"] = await exp_a3()

    a4_charts(results["default"], results["spread"])

    (RES / "summary.json").write_text(json.dumps(results, indent=2))
    print(f"\n✓ figures -> {FIG}\n✓ summary -> {RES / 'summary.json'}")


if __name__ == "__main__":
    asyncio.run(main())
