"""Scripted approval policy for non-interactive evaluation runs."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Any

FILE_TOOLS = {"write_file", "edit_file", "delete"}
PROTECTED_NAMES = {".git", ".env"}
PATH_COMMANDS = {"cp", "mv", "touch", "mkdir"}
FORBIDDEN_COMMAND_TOKENS = (
    "\n",
    "\r",
    "\x00",
    "&&",
    "||",
    ";",
    "|",
    "&",
    ">",
    "<",
    "`",
    "$",
    "~",
)
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


def _normalise_path(value: Any) -> str | None:
    raw = str(value or "").replace("\\", "/")
    parts = PurePosixPath(raw).parts
    if any(part == ".." for part in parts):
        return None
    cleaned = [part for part in parts if part not in {"", "/", "."}]
    return "/".join(cleaned) if cleaned else None


def _is_protected(path: str) -> bool:
    for part in PurePosixPath(path).parts:
        lowered = part.lower()
        if lowered in PROTECTED_NAMES or lowered.startswith(".env."):
            return True
    return False


def _command_path_allowed(value: str) -> bool:
    if value.startswith(("/", "\\")) or re.match(r"^[a-z]:[\\/]", value):
        return False
    path = _normalise_path(value)
    return path is not None and not _is_protected(path)


def _command_allowed(command: str) -> tuple[bool, str]:
    lowered = command.strip().lower()
    if any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS):
        return False, "shell control characters are not allowed"
    try:
        tokens = shlex.split(lowered)
    except ValueError:
        return False, "command cannot be parsed"
    if not tokens:
        return False, "empty command"
    if not any(
        lowered == prefix or lowered.startswith(prefix + " ")
        for prefix in APPROVED_COMMAND_PREFIXES
    ):
        return False, "command prefix is not in the eval allow-list"

    if tokens[0] in PATH_COMMANDS:
        for token in tokens[1:]:
            if token == "--":
                continue
            if token.startswith("-"):
                if "=" in token:
                    value = token.split("=", 1)[1]
                    if value and not _command_path_allowed(value):
                        return False, f"command path is not allowed: {value}"
                continue
            if not _command_path_allowed(token):
                return False, f"command path is not allowed: {token}"
    return True, ""


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
        raw_path = args.get("file_path") or args.get("path")
        path = _normalise_path(raw_path)
        if path is None:
            return "reject", f"invalid or escaping file path: {raw_path!r}"
        if _is_protected(path):
            return "reject", f"protected path: {path}"
        return "approve", f"workspace file change: {path}"

    if name == "execute":
        command = str(args.get("command", ""))
        allowed, reason = _command_allowed(command)
        if allowed:
            return "approve", f"development command: {command}"
        return "reject", f"command is outside the eval allow-list: {command} ({reason})"

    return "reject", f"unsupported gated tool: {name}"
