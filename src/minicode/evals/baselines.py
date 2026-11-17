"""Baseline registry for MiniCode task evals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Baseline:
    """One runnable evaluation baseline."""

    name: str
    kind: str
    permission_mode: str | None = None
    checkpoint: bool = False
    approval_policy: str | None = None


BASELINES = {
    "bare": Baseline("bare", "bare"),
    "deepagents-default": Baseline("deepagents-default", "deepagents"),
    "minicode-yolo": Baseline(
        "minicode-yolo",
        "minicode",
        permission_mode="yolo",
        checkpoint=True,
    ),
    "minicode-ask": Baseline(
        "minicode-ask",
        "minicode",
        permission_mode="ask",
        checkpoint=True,
        approval_policy="eval",
    ),
    "minicode-no-checkpoint": Baseline(
        "minicode-no-checkpoint",
        "minicode",
        permission_mode="yolo",
        checkpoint=False,
    ),
}

ALIASES = {"full": "minicode-yolo"}

ALL_BASELINES = ["full", "bare"]
MATRIX_BASELINES = [
    "bare",
    "deepagents-default",
    "minicode-yolo",
    "minicode-ask",
    "minicode-no-checkpoint",
]
BASELINE_CHOICES = [
    "full",
    "bare",
    "deepagents-default",
    "minicode-yolo",
    "minicode-ask",
    "minicode-no-checkpoint",
    "all",
    "matrix",
]
WORKER_BASELINE_CHOICES = [
    "full",
    "bare",
    "deepagents-default",
    "minicode-yolo",
    "minicode-ask",
    "minicode-no-checkpoint",
]


def resolve_baseline(name: str) -> Baseline:
    """Return the baseline config for ``name``, following aliases."""
    canonical = ALIASES.get(name, name)
    baseline = BASELINES.get(canonical)
    if baseline is None:
        raise ValueError(f"unknown baseline: {name}")
    return baseline


def resolve_baselines(names: list[str]) -> list[str]:
    """Expand ``all`` / ``matrix`` and remove duplicates."""
    resolved: list[str] = []
    for name in names:
        if name == "all":
            expanded = ALL_BASELINES
        elif name == "matrix":
            expanded = MATRIX_BASELINES
        else:
            expanded = [name]
        for item in expanded:
            resolve_baseline(item)
            if item not in resolved:
                resolved.append(item)
    return resolved
