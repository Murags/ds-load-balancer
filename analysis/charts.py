"""Matplotlib chart helpers for the Task 4 experiments."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt


def bar_distribution(counts: dict[str, int], title: str, path: str) -> None:
    """A-1: per-server request counts as a bar chart."""
    servers = list(counts.keys())
    values = [counts[s] for s in servers]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(servers, values, color="#4C72B0")
    ax.set_xlabel("Server replica")
    ax.set_ylabel("Requests handled")
    ax.set_title(title)
    ax.bar_label(bars, fmt="%d", padding=3)
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def grouped_bar(
    labels: list[str],
    series: dict[str, list[float]],
    title: str,
    ylabel: str,
    path: str,
) -> None:
    """A-4: side-by-side bars for two variants (e.g. default vs spread)."""
    import numpy as np

    x = np.arange(len(labels))
    width = 0.8 / max(1, len(series))
    fig, ax = plt.subplots(figsize=(8, 5))
    for idx, (name, values) in enumerate(series.items()):
        ax.bar(x + idx * width, values, width, label=name)
    ax.set_xticks(x + width * (len(series) - 1) / 2)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def line_loads(
    n_values: list[int],
    series: dict[str, list[float]],
    title: str,
    ylabel: str,
    path: str,
) -> None:
    """A-2/A-4: metric vs N as a line chart (one line per series)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    for name, values in series.items():
        ax.plot(n_values, values, marker="o", label=name)
    ax.set_xlabel("Number of server containers (N)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(n_values)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
