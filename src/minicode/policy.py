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

_RAW_DENY_PATTERNS = (
    re.compile(r"\|\s*(?:sh|bash|zsh|pwsh|powershell|iex|invoke-expression)\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&", re.IGNORECASE),
)

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\n|&|\|")
_REDIRECT_PATTERN = re.compile(r"(?<![<>&])>{1,2}|<")
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
_SHELL_META_PATTERN = re.compile(r"[$`()&]")
_SAFE_ARG_DENY = ("--pre", "--output", "--ext-diff", "-exec", "-delete")
_CATASTROPHIC_TARGETS = {"/", "/*", "~", "~/", "..", "../", ".", "./", "*"}


def _segments(command: str) -> list[str]:
    return [segment.strip() for segment in _SEGMENT_SPLIT.split(command) if segment.strip()]


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _first_token(segment: str) -> str:
    parts = _tokens(segment)
    return parts[0].lower() if parts else ""


def _short_flag(flag: str, letter: str) -> bool:
    return flag.startswith("-") and not flag.startswith("--") and letter in flag[1:].lower()


def _rm_denied(rest: list[str]) -> bool:
    flags = [item for item in rest if item.startswith("-")]
    targets = [item for item in rest if not item.startswith("-")]
    recursive = any(item == "--recursive" or _short_flag(item, "r") for item in flags)
    catastrophic = any(item in _CATASTROPHIC_TARGETS or item.startswith("/*") for item in targets)
    if recursive and catastrophic:
        return True
    return "--no-preserve-root" in flags and any(
        item in {"/", "/*"} or item.startswith("/*") for item in targets
    )


def _del_denied(rest: list[str]) -> bool:
    flags = {item.lower() for item in rest if item.startswith("/")}
    targets = [item for item in rest if not item.startswith("/")]
    root_target = any(re.fullmatch(r"[a-z]:\\?", item, re.IGNORECASE) for item in targets)
    return ("/s" in flags or "/q" in flags) and root_target


def _rd_denied(rest: list[str]) -> bool:
    return _del_denied(rest)


def _segment_hard_denied(segment: str) -> bool:
    tokens = _tokens(segment)
    if not tokens:
        return False
    first = tokens[0].lower()
    rest = [item.lower() for item in tokens[1:]]

    if first in {"shutdown", "reboot", "fdisk", "diskpart"}:
        return True
    if first.startswith("mkfs"):
        return True
    if first == "format" and any(re.fullmatch(r"[a-z]:\\?", item) for item in rest):
        return True
    if first == "dd" and any(item.startswith("of=/dev/") for item in rest):
        return True
    if first == "rm":
        return _rm_denied(rest)
    if first == "del":
        return _del_denied(rest)
    if first in {"rd", "rmdir"}:
        return _rd_denied(rest)
    if first == "git" and len(tokens) >= 2 and tokens[1].lower() == "push":
        return any(item in {"--force", "-f"} or item.startswith("--force=") for item in rest)
    if first == "chmod" and "-r" in rest and "777" in rest and "/" in rest:
        return True
    if first in {"iex", "invoke-expression"}:
        return True
    if first in {"powershell", "pwsh"} and any(
        item in {"-enc", "-encodedcommand"} or item.startswith("-enc") for item in rest
    ):
        return True
    return False


def _is_hard_denied(command: str) -> bool:
    if any(pattern.search(command) for pattern in _RAW_DENY_PATTERNS):
        return True
    return any(_segment_hard_denied(segment) for segment in _segments(command))


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

        if _is_hard_denied(normalized):
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
        if _REDIRECT_PATTERN.search(command) or _SHELL_META_PATTERN.search(command):
            return False
        segments = _segments(command)
        if not segments:
            return False
        for segment in segments:
            if any(arg in segment.lower() for arg in _SAFE_ARG_DENY):
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
