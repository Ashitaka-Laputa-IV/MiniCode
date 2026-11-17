"""Failure classification and aggregation helpers for evaluation results."""

from __future__ import annotations

from collections import Counter
from statistics import pstdev
from typing import Any

FAILURE_REASONS = (
    "passed",
    "timeout",
    "tool_limit",
    "permission_denied",
    "loop",
    "no_tests_run",
    "context_overflow",
    "verification_failed",
    "agent_error",
)


def classify_failure(result: dict[str, Any], trace: dict[str, Any] | None = None) -> str:
    """Classify one result using worker, verify, and trace evidence."""
    if result.get("passed"):
        return "passed"

    trace = trace or {}
    error = str(result.get("error") or "").lower()
    verify_output = str(result.get("verify_output") or "").lower()

    if "timed out" in error or "timed out" in verify_output:
        return "timeout"
    if "tool call limit" in error:
        return "tool_limit"
    if "context" in error and any(word in error for word in ("overflow", "window", "too long")):
        return "context_overflow"

    if not result.get("worker_ok"):
        return "agent_error"

    if trace.get("blocked", 0) or trace.get("rejections", 0):
        return "permission_denied"
    if trace.get("repeated_tool_calls"):
        return "loop"
    if trace.get("ran_tests") is False:
        return "no_tests_run"
    return "verification_failed"


def failure_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    """Count failure reasons for results that did not pass."""
    counts = Counter(
        str(result.get("failure_reason") or "unknown")
        for result in results
        if not result.get("passed")
    )
    return dict(sorted(counts.items()))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    return round(pstdev(values), 4) if len(values) > 1 else 0.0


def pass_at_k(results: list[dict[str, Any]], k: int) -> tuple[float, float]:
    """Return mean and population std of per-task any-pass over ``k`` runs."""
    by_task: dict[str, list[bool]] = {}
    for index, result in enumerate(results):
        task_id = str(result.get("id") or f"task-{index}")
        by_task.setdefault(task_id, []).append(bool(result.get("passed")))
    indicators = [1.0 if any(flags[:k]) else 0.0 for flags in by_task.values()]
    return round(_mean(indicators), 4), _std(indicators)
