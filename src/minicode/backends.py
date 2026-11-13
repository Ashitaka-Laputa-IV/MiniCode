"""Shell backend with MiniCode permission policy enforcement."""

from __future__ import annotations

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import DeleteResult, EditResult, ExecuteResponse, WriteResult

from .policy import DecisionAction, Policy


class PolicyShellBackend(LocalShellBackend):
    """Local shell backend with MiniCode policy enforcement."""

    def __init__(self, *, policy: Policy, **kwargs) -> None:
        super().__init__(**kwargs)
        self._policy = policy

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        decision = self._policy.evaluate_command(command)
        if decision.action == DecisionAction.DENY:
            return ExecuteResponse(
                output=f"Blocked by permission policy: {decision.reason}",
                exit_code=126,
                truncated=False,
            )
        return super().execute(command, timeout=timeout)

    def write(self, file_path: str, content: str) -> WriteResult:
        if not self._policy.allows_file_write():
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
        if not self._policy.allows_file_write():
            return EditResult(
                error=f"Blocked by permission policy: edits are disabled ({file_path})"
            )
        return super().edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        if not self._policy.allows_file_write():
            return DeleteResult(
                error=f"Blocked by permission policy: deletes are disabled ({file_path})"
            )
        return super().delete(file_path)
