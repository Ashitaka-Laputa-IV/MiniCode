"""Scripted approval policy for non-interactive evaluation runs."""

from __future__ import annotations

from typing import Any

FILE_TOOLS = {"write_file", "edit_file", "delete"}
PROTECTED_PATHS = (".git", ".env")
APPROVED_COMMAND_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python -m unittest",
    "python -m compileall",
    "uv run pytest",
    "uv run ruff",
    "ruff",
    "mkdir",
    "mv",
    "cp",
    "touch",
)


def _normalise_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").lstrip("/")


def _is_protected(path: str) -> bool:
    lowered = path.lower()
    return any(
        lowered == prefix or lowered.startswith(prefix + "/") or lowered.startswith(prefix + ".")
        for prefix in PROTECTED_PATHS
    )


def _command_allowed(command: str) -> bool:
    lowered = command.strip().lower()
    if any(token in lowered for token in ("&&", "||", ";", "|", "&", ">", "<", "`", "$(")):
        return False
    return any(
        lowered == prefix or lowered.startswith(prefix + " ")
        for prefix in APPROVED_COMMAND_PREFIXES
    )


def decide(action: dict[str, Any], *, policy: str | None = "eval") -> tuple[str, str]:
    """Return ``(decision, reason)`` for one gated action.

    The evaluation approver is cooperative for ordinary coding work but rejects
    protected paths and commands outside a small development allow-list.
    """
    if policy != "eval":
        return "reject", f"unsupported approval policy: {policy!r}"

    name = str(action.get("name", ""))
    args = action.get("args") or {}
    if not isinstance(args, dict):
        return "reject", "tool arguments are not a mapping"

    if name in FILE_TOOLS:
        path = _normalise_path(args.get("file_path") or args.get("path"))
        if not path:
            return "reject", "file path is missing"
        if _is_protected(path):
            return "reject", f"protected path: {path}"
        return "approve", f"workspace file change: {path}"

    if name == "execute":
        command = str(args.get("command", ""))
        if _command_allowed(command):
            return "approve", f"development command: {command}"
        return "reject", f"command is outside the eval allow-list: {command}"

    return "reject", f"unsupported gated tool: {name}"
