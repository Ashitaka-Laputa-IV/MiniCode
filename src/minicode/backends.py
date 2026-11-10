"""Shell backend with MiniCode permission policy enforcement."""

from __future__ import annotations

import time

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import DeleteResult, EditResult, ExecuteResponse, WriteResult

from .audit import AuditLogger
from .policy import DecisionAction, Policy
from .redaction import redact_text, summarize_args, utf8_len


class PolicyShellBackend(LocalShellBackend):
    """Local shell backend with MiniCode policy enforcement."""

    def __init__(
        self,
        *,
        policy: Policy,
        audit: AuditLogger | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._policy = policy
        self._audit = audit

    def _log_policy(
        self,
        tool: str,
        decision: str,
        reason: str,
        args: dict,
    ) -> None:
        if self._audit is not None:
            self._audit.log(
                "policy",
                tool=tool,
                decision=decision,
                reason=reason,
                args=args,
            )

    def _log_result(
        self,
        tool: str,
        *,
        ok: bool,
        duration_ms: float,
        error: str | None = None,
        **fields,
    ) -> None:
        if self._audit is not None:
            self._audit.log(
                "result",
                tool=tool,
                ok=ok,
                duration_ms=duration_ms,
                error=redact_text(error) if error else None,
                **fields,
            )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        started = time.perf_counter()
        decision = self._policy.evaluate_command(command)
        self._log_policy(
            "execute",
            decision.action.value,
            decision.reason,
            summarize_args("execute", {"command": command}),
        )
        if decision.action == DecisionAction.DENY:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            self._log_result(
                "execute",
                ok=False,
                duration_ms=duration_ms,
                error=decision.reason,
                exit_code=126,
            )
            return ExecuteResponse(
                output=f"Blocked by permission policy: {decision.reason}",
                exit_code=126,
                truncated=False,
            )
        response = super().execute(command, timeout=timeout)
        self._log_result(
            "execute",
            ok=response.exit_code == 0,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            exit_code=response.exit_code,
            error=None if response.exit_code == 0 else "command failed",
        )
        return response

    def write(self, file_path: str, content: str) -> WriteResult:
        started = time.perf_counter()
        if not self._policy.allows_file_write():
            self._log_policy(
                "write_file",
                "deny",
                "writes are disabled in read-only mode",
                summarize_args("write_file", {"file_path": file_path, "content": content}),
            )
            result = WriteResult(
                error=f"Blocked by permission policy: writes are disabled ({file_path})"
            )
        else:
            self._log_policy(
                "write_file",
                "allow",
                "policy allows writes",
                summarize_args("write_file", {"file_path": file_path, "content": content}),
            )
            result = super().write(file_path, content)
        self._log_result(
            "write_file",
            ok=result.error is None,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            error=result.error,
            path=redact_text(file_path),
            bytes=utf8_len(content),
        )
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        started = time.perf_counter()
        args = {
            "file_path": file_path,
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        }
        if not self._policy.allows_file_write():
            self._log_policy(
                "edit_file",
                "deny",
                "edits are disabled in read-only mode",
                summarize_args("edit_file", args),
            )
            result = EditResult(
                error=f"Blocked by permission policy: edits are disabled ({file_path})"
            )
        else:
            self._log_policy(
                "edit_file",
                "allow",
                "policy allows edits",
                summarize_args("edit_file", args),
            )
            result = super().edit(file_path, old_string, new_string, replace_all)
        self._log_result(
            "edit_file",
            ok=result.error is None,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            error=result.error,
            path=redact_text(file_path),
        )
        return result

    def delete(self, file_path: str) -> DeleteResult:
        started = time.perf_counter()
        if not self._policy.allows_file_write():
            self._log_policy(
                "delete",
                "deny",
                "deletes are disabled in read-only mode",
                summarize_args("delete", {"file_path": file_path}),
            )
            result = DeleteResult(
                error=f"Blocked by permission policy: deletes are disabled ({file_path})"
            )
        else:
            self._log_policy(
                "delete",
                "allow",
                "policy allows deletes",
                summarize_args("delete", {"file_path": file_path}),
            )
            result = super().delete(file_path)
        self._log_result(
            "delete",
            ok=result.error is None,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            error=result.error,
            path=redact_text(file_path),
        )
        return result
