"""Permission modes and shell command policy for MiniCode."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import Enum


class PermissionMode(str, Enum):
    """How much human oversight a session requires."""

    READ_ONLY = "read-only"
    ASK = "ask"
    YOLO = "yolo"

    @classmethod
    def parse(cls, value: str | PermissionMode | None) -> PermissionMode:
        if isinstance(value, cls):
            return value
        raw = (value or "ask").strip().lower()
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(f"invalid permission mode {value!r}; choose {choices}") from exc


class DecisionAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    action: DecisionAction
    reason: str


SAFE_COMMAND_PREFIXES = (
    "ls",
    "dir",
    "pwd",
    "cd",
    "cat",
    "type",
    "head",
    "tail",
    "more",
    "less",
    "grep",
    "rg",
    "find",
    "where",
    "which",
    "whoami",
    "git status",
    "git diff",
    "git log",
    "git show",
    "git rev-parse",
    "git branch --show-current",
    "uv --version",
    "python --version",
    "python3 --version",
    "node --version",
)

NETWORK_COMMANDS = frozenset(
    {
        "curl",
        "wget",
        "ssh",
        "scp",
        "sftp",
        "ftp",
        "nc",
        "netcat",
        "telnet",
    }
)

NETWORK_PREFIXES = (
    "pip install",
    "pip3 install",
    "uv add",
    "uv remove",
    "uv sync",
    "npm install",
    "npm uninstall",
    "pnpm add",
    "pnpm install",
    "yarn add",
    "yarn install",
    "cargo install",
    "go get",
    "git clone",
    "git fetch",
    "git pull",
    "git push",
)

MUTATING_COMMANDS = frozenset(
    {
        "rm",
        "del",
        "rd",
        "rmdir",
        "mv",
        "move",
        "cp",
        "copy",
        "mkdir",
        "md",
        "touch",
        "chmod",
        "chown",
        "python",
        "python3",
        "node",
        "powershell",
        "pwsh",
        "cmd",
        "bash",
        "sh",
    }
)

MUTATING_PREFIXES = (
    "git commit",
    "git reset",
    "git clean",
    "git checkout",
    "git switch",
    "git merge",
    "git rebase",
    "git cherry-pick",
)

_DENY_PATTERNS = (
    re.compile(r"\brm\s+(?:-[a-z]*[rf][a-z]*\s+)+(?:/|~|\*|\.\.?)(?:\s|$)", re.IGNORECASE),
    re.compile(
        r"\brm\s+--(?:recursive|force)\b[^\n;&|]*(?:\s/|\s~|\s\*|\s\.\.?)(?:\s|$)", re.IGNORECASE
    ),
    re.compile(r"\bdel\s+/[fsq]\b[^\n;&|]*\b[a-z]:\\?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\b(?:rd|rmdir)\s+/s\b[^\n;&|]*\b[a-z]:\\?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:\\?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\b(?:mkfs|fdisk|diskpart)\b", re.IGNORECASE),
    re.compile(r"\bdd\b[^\n;&|]*\bof=/dev/", re.IGNORECASE),
    re.compile(r"\b(?:shutdown|reboot)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\s+(?:--force|-f)\b", re.IGNORECASE),
    re.compile(r"\bpowershell(?:\.exe)?\b[^\n;&|]*(?:-enc|-encodedcommand)\b", re.IGNORECASE),
    re.compile(r"\|\s*(?:sh|bash|zsh|pwsh|powershell|iex|invoke-expression)\b", re.IGNORECASE),
    re.compile(r"\b(?:iex|invoke-expression)\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&", re.IGNORECASE),
    re.compile(r"\bchmod\s+-R\s+777\s+/(?:\s|$)", re.IGNORECASE),
)

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\n|\|")
_REDIRECT_PATTERN = re.compile(r"(?<![<>&])>{1,2}|<")
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)


def _segments(command: str) -> list[str]:
    return [segment.strip() for segment in _SEGMENT_SPLIT.split(command) if segment.strip()]


def _first_token(segment: str) -> str:
    try:
        parts = shlex.split(segment, posix=True)
    except ValueError:
        parts = segment.split()
    return parts[0].lower() if parts else ""


def _matches_prefix(segment: str, prefix: str) -> bool:
    lowered = segment.lower()
    return lowered == prefix or lowered.startswith(prefix + " ")


class Policy:
    """Classify shell commands and decide whether to allow, ask, or deny."""

    def __init__(
        self,
        mode: str | PermissionMode = PermissionMode.ASK,
        *,
        allow_commands: str | list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.mode = PermissionMode.parse(mode)
        builtin = list(SAFE_COMMAND_PREFIXES)
        allow_all = False
        extra: list[str] = []

        if isinstance(allow_commands, str):
            items = [item.strip() for item in allow_commands.split(",")]
        else:
            items = [str(item).strip() for item in (allow_commands or [])]

        for item in items:
            if not item:
                continue
            lowered = item.lower()
            if lowered == "all":
                allow_all = True
            elif lowered == "recommended":
                continue
            else:
                extra.append(lowered)

        self._allow_commands = tuple(dict.fromkeys([*builtin, *extra]))
        self._allow_all = allow_all

    def evaluate_command(self, command: str) -> Decision:
        normalized = command.strip()
        if not normalized:
            return Decision(DecisionAction.DENY, "empty command")

        for pattern in _DENY_PATTERNS:
            if pattern.search(normalized):
                return Decision(DecisionAction.DENY, "command matched the hard deny-list")

        if self.mode == PermissionMode.YOLO:
            return Decision(DecisionAction.ALLOW, "yolo mode")

        if self._allow_all and self.mode != PermissionMode.READ_ONLY:
            return Decision(DecisionAction.ALLOW, "allow-list permits all commands")

        if self._is_safe(normalized):
            return Decision(DecisionAction.ALLOW, "command is on the safe allow-list")

        network = self._is_network(normalized)
        mutating = self._is_mutating(normalized)

        if self.mode == PermissionMode.READ_ONLY:
            if network:
                reason = "read-only mode blocks network commands"
            elif mutating:
                reason = "read-only mode blocks mutating commands"
            else:
                reason = "read-only mode only permits safe commands"
            return Decision(DecisionAction.DENY, reason)

        if network:
            return Decision(DecisionAction.ASK, "command may use the network")
        if mutating:
            return Decision(DecisionAction.ASK, "command may modify the workspace or system")
        return Decision(DecisionAction.ASK, "command is not on the allow-list")

    def needs_approval(self, command: str) -> bool:
        return (
            self.mode == PermissionMode.ASK
            and self.evaluate_command(command).action == DecisionAction.ASK
        )

    def allows_file_write(self) -> bool:
        return self.mode != PermissionMode.READ_ONLY

    def _is_safe(self, command: str) -> bool:
        if _REDIRECT_PATTERN.search(command):
            return False
        segments = _segments(command)
        if not segments:
            return False
        return all(
            any(_matches_prefix(segment, prefix) for prefix in self._allow_commands)
            for segment in segments
        )

    def _is_network(self, command: str) -> bool:
        if _URL_PATTERN.search(command):
            return True
        for segment in _segments(command):
            lowered = segment.lower()
            if _first_token(segment) in NETWORK_COMMANDS:
                return True
            if any(_matches_prefix(lowered, prefix) for prefix in NETWORK_PREFIXES):
                return True
        return False

    def _is_mutating(self, command: str) -> bool:
        if _REDIRECT_PATTERN.search(command):
            return True
        for segment in _segments(command):
            lowered = segment.lower()
            if _first_token(segment) in MUTATING_COMMANDS:
                return True
            if any(_matches_prefix(lowered, prefix) for prefix in MUTATING_PREFIXES):
                return True
        return False
