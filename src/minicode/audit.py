"""Optional Tracekit audit integration for MiniCode runs.

Tracekit records tool calls in a signed, tamper-evident run. It is opt-in so
normal MiniCode runs stay offline and do not depend on a signer process.
"""

from __future__ import annotations

import os
from typing import Any


class AuditError(RuntimeError):
    """Raised when a requested Tracekit audit run cannot be started."""


def start_audit() -> Any:
    """Start a Tracekit run for this process and return its handle.

    Tracekit patches LangGraph's ``ToolNode`` when instrumented. Call this
    before ``build_agent`` so Deep Agents creates its tool nodes afterwards.
    """
    try:
        import tracekit
    except ImportError as exc:
        raise AuditError(
            "Tracekit audit support is not installed; run `uv sync` or `uv add tracekit-ai`."
        ) from exc

    try:
        run = tracekit.instrument()  # type: ignore[attr-defined]
    except Exception as exc:
        raise AuditError(f"could not start the Tracekit audit run: {exc}") from exc

    if run is None:
        raise AuditError(
            "Tracekit did not wire any framework; install the LangGraph "
            "adapter dependencies or remove --audit."
        )
    return run


def audit_hint(run: Any) -> str:
    """Return a short hint telling the user how to inspect the recorded run."""
    run_id = getattr(run, "run_id", None)
    suffix = f" (run {run_id})" if run_id else ""
    if os.environ.get("TRACEKIT_SIGNER"):
        return f"audit run recorded{suffix}; view with: tracekit view --config <signer.yaml>"
    return f"audit run recorded{suffix}; verify with: tracekit last"
