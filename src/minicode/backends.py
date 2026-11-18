"""Shell backend with MiniCode permission policy enforcement."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import DeleteResult, EditResult, ExecuteResponse, WriteResult

from .policy import DecisionAction, Policy

TraceSink = Callable[[str, dict[str, Any]], None]


class PolicyShellBackend(LocalShellBackend):
    """Local shell backend with MiniCode policy enforcement."""

    def __init__(
        self,
        *,
        policy: Policy,
        trace_sink: TraceSink | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._policy = policy
        self._trace_sink = trace_sink

    def _emit(self, event: str, **data: Any) -> None:
        if self._trace_sink is not None:
            self._trace_sink(event, data)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        decision = self._policy.evaluate_command(command)
        self._emit(
            "policy_decision",
            tool="execute",
            command=command,
            action=decision.action.value.upper(),
            reason=decision.reason,
        )
        if decision.action == DecisionAction.DENY:
            return ExecuteResponse(
                output=f"Blocked by permission policy: {decision.reason}",
                exit_code=126,
                truncated=False,
            )
        return super().execute(command, timeout=timeout)

    def write(self, file_path: str, content: str) -> WriteResult:
        allowed = self._policy.allows_file_write()
        self._emit(
            "policy_decision",
            tool="write_file",
            path=file_path,
            action="ALLOW" if allowed else "DENY",
            reason="writes are enabled" if allowed else "writes are disabled",
        )
        if not allowed:
            return WriteResult(
                error=f"Blocked by permission policy: writes are disabled ({file_path})"
            )
        return super().write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        allowed = self._policy.allows_file_write()
        self._emit(
            "policy_decision",
            tool="edit_file",
            path=file_path,
            action="ALLOW" if allowed else "DENY",
            reason="edits are enabled" if allowed else "edits are disabled",
        )
        if not allowed:
            return EditResult(
                error=f"Blocked by permission policy: edits are disabled ({file_path})"
            )
        return super().edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        allowed = self._policy.allows_file_write()
        self._emit(
            "policy_decision",
            tool="delete",
            path=file_path,
            action="ALLOW" if allowed else "DENY",
            reason="deletes are enabled" if allowed else "deletes are disabled",
        )
        if not allowed:
            return DeleteResult(
                error=f"Blocked by permission policy: deletes are disabled ({file_path})"
            )
        return super().delete(file_path)
