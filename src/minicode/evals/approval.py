"""Scripted approval policy for non-interactive evaluation runs."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import Any

FILE_TOOLS = {"write_file", "edit_file", "delete"}
PROTECTED_NAMES = {".git", ".env"}
PATH_COMMANDS = {"cp", "mv", "touch", "mkdir"}
GLOB_CHARS = frozenset("*?[]{}")
WINDOWS_INVALID_PATH_CHARS = frozenset('<>:"|?*')
SHORT_NAME_RE = re.compile(r"~\d+")
RECURSIVE_LONG_OPTIONS = frozenset({"--archive", "--recursive"})
PATH_SHORT_FLAGS = {
    # -a, -r, and -R are intentionally omitted: recursive copies can bypass
    # checks for protected files inside the source directory. Symlink-related
    # flags (-d/-l/-s/-L/-P/-H) are also omitted so a safe-looking path cannot
    # dereference or link to a protected file.
    "cp": frozenset("bfinpuvxT"),
    "mv": frozenset("bfinuvT"),
    "touch": frozenset("acfhm"),
    "mkdir": frozenset("pv"),
}
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
    "%",
    "^",
    "!",
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
    if not raw or any(ord(char) < 32 for char in raw) or raw.startswith("//"):
        return None
    parts = PurePosixPath(raw).parts
    if any(part == ".." for part in parts):
        return None
    cleaned: list[str] = []
    for part in parts:
        if part in {"", "/", "."}:
            continue
        # Windows ignores alternate data streams, 8.3 aliases, and trailing
        # spaces/dots when resolving a path. Reject or normalise them before
        # checking protected names so those spellings cannot bypass .env/.git.
        if any(char in WINDOWS_INVALID_PATH_CHARS for char in part):
            return None
        if SHORT_NAME_RE.search(part):
            return None
        normalised = part.rstrip(" .")
        if normalised in {"", ".", ".."}:
            return None
        cleaned.append(normalised)
    return "/".join(cleaned) if cleaned else None


def _is_protected(path: str) -> bool:
    for part in PurePosixPath(path).parts:
        lowered = part.casefold().rstrip(" .")
        if lowered in PROTECTED_NAMES or lowered.startswith(".env."):
            return True
    return False


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _short_options_allowed(command_name: str, token: str) -> bool:
    """Reject short options that can carry an attached path argument.

    Attached values such as ``cp -t/tmp`` bypass a separate path check, so only
    well-known boolean flag clusters are accepted for path commands.
    """
    if token == "-" or not token.startswith("-") or token.startswith("--"):
        return True
    letters = token[1:].split("=", 1)[0]
    allowed = PATH_SHORT_FLAGS.get(command_name, frozenset())
    return bool(letters) and all(letter in allowed for letter in letters)


def _long_option_allowed(command_name: str, token: str) -> bool:
    if command_name not in {"cp", "mv"}:
        return True
    option = token.split("=", 1)[0].casefold()
    # Long options may be abbreviated by GNU tools, so reject any prefix of
    # --archive/--recursive as well as the full spelling.
    return not any(full.startswith(option) for full in RECURSIVE_LONG_OPTIONS)


def _command_path_allowed(value: str) -> bool:
    value = _strip_quotes(value)
    if not value or any(char in value for char in GLOB_CHARS):
        return False
    if value.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:", value):
        return False
    path = _normalise_path(value)
    return path is not None and not _is_protected(path)


def _path_tokens_allowed(
    tokens: list[str], raw_tokens: list[str], command_name: str
) -> tuple[bool, str]:
    end_options = False
    for token in tokens:
        if token == "--":
            end_options = True
            continue
        if not end_options and token.startswith("-") and token != "-":
            if token.startswith("--"):
                if not _long_option_allowed(command_name, token):
                    return False, f"recursive command option is not allowed: {token}"
                if "=" in token:
                    value = token.split("=", 1)[1]
                    if value and not _command_path_allowed(value):
                        return False, f"command path is not allowed: {value}"
                continue
            if not _short_options_allowed(command_name, token):
                return False, f"short option is not allowed: {token}"
            if "=" in token:
                value = token.split("=", 1)[1]
                if value and not _command_path_allowed(value):
                    return False, f"command path is not allowed: {value}"
            continue
        if not _command_path_allowed(token):
            return False, f"command path is not allowed: {token}"

    # POSIX shlex consumes backslashes, so inspect raw tokens too. This keeps
    # Windows paths such as ``..\outside`` from becoming ``..outside``.
    end_options = False
    for token in raw_tokens:
        raw = _strip_quotes(token)
        if raw == "--":
            end_options = True
            continue
        if not end_options and raw.startswith("-") and raw != "-":
            if raw.startswith("--"):
                if not _long_option_allowed(command_name, raw):
                    return False, f"recursive command option is not allowed: {raw}"
                if "=" in raw:
                    value = _strip_quotes(raw.split("=", 1)[1])
                    if value and not _command_path_allowed(value):
                        return False, f"command path is not allowed: {value}"
                continue
            if not _short_options_allowed(command_name, raw):
                return False, f"short option is not allowed: {raw}"
            if "=" in raw:
                value = _strip_quotes(raw.split("=", 1)[1])
                if value and not _command_path_allowed(value):
                    return False, f"command path is not allowed: {value}"
            continue
        if not _command_path_allowed(raw):
            return False, f"command path is not allowed: {raw}"
    return True, ""


def _command_allowed(command: str) -> tuple[bool, str]:
    stripped = command.strip()
    lowered = stripped.lower()
    if any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS):
        return False, "shell control characters are not allowed"
    try:
        tokens = shlex.split(stripped)
        raw_tokens = shlex.split(stripped, posix=False)
    except ValueError:
        return False, "command cannot be parsed"
    if not tokens or not raw_tokens:
        return False, "empty command"
    if not any(
        lowered == prefix or lowered.startswith(prefix + " ")
        for prefix in APPROVED_COMMAND_PREFIXES
    ):
        return False, "command prefix is not in the eval allow-list"

    command_name = tokens[0].lower()
    if command_name in PATH_COMMANDS:
        allowed, reason = _path_tokens_allowed(tokens[1:], raw_tokens[1:], command_name)
        if not allowed:
            return False, reason
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
