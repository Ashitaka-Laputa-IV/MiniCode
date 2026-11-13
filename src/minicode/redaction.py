"""Secret redaction for audit logs and approval output."""

from __future__ import annotations

import re
from typing import Any

# Allow a non-letter prefix (quotes, =, _, path separators), but do not treat
# the suffix of an ordinary word such as "risk-management" as a token.
_TOKEN_PATTERNS = (
    re.compile(r"(?<![A-Za-z])sk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?<![A-Za-z])gh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?<![A-Za-z])github_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?<![A-Za-z])xox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"(?<![A-Za-z])AKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?<![A-Za-z])AIza[0-9A-Za-z_-]{20,}\b"),
)
_SENSITIVE_KEY_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)")

_BEARER_PATTERN = re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._~+/=-]{8,})")
_URL_CREDENTIALS = re.compile(r"(?i)(https?://[^/\s:@]+:)([^@\s/]+)(@)")
_AUTH_HEADER = re.compile(r"(?i)\b(authorization\s*:\s*)[^\r\n]+")
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<key_quote>['\"]?)"
    r"(?P<key>[A-Za-z0-9_]*(?:api[_-]?key|token|secret|password|passwd)[A-Za-z0-9_]*)"
    r"(?P=key_quote)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?:"
    r"(?P<value_quote>['\"])(?P<quoted_value>.*?)(?P=value_quote)"
    r"|(?P<plain_value>[^\s'\";]+)"
    r")"
)
_CLI_SECRET_ARG = re.compile(
    r"(?i)(--[a-z0-9-]*(?:key|token|secret|password)[a-z0-9-]*)(\s+|=)(\S+)"
)


def _redact_assignment(match: re.Match[str]) -> str:
    key_quote = match.group("key_quote")
    prefix = f"{key_quote}{match.group('key')}{key_quote}{match.group('separator')}"
    value_quote = match.group("value_quote")
    if value_quote:
        return f"{prefix}{value_quote}***{value_quote}"
    return f"{prefix}***"


def redact_text(text: str) -> str:
    """Best-effort removal of common credentials from log/display text."""
    redacted = _URL_CREDENTIALS.sub(r"\1***\3", text)
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub("***", redacted)
    redacted = _BEARER_PATTERN.sub(r"\1***", redacted)
    redacted = _AUTH_HEADER.sub(r"\1***", redacted)
    redacted = _ASSIGNMENT_PATTERN.sub(_redact_assignment, redacted)
    redacted = _CLI_SECRET_ARG.sub(
        lambda match: f"{match.group(1)}{match.group(2)}***",
        redacted,
    )
    return redacted


def utf8_len(value: Any) -> int | None:
    """Return the UTF-8 byte length for strings, else None."""
    return len(value.encode("utf-8")) if isinstance(value, str) else None


def redact_value(value: Any, *, limit: int | None = None) -> Any:
    """Recursively redact strings in JSON-compatible values."""
    if isinstance(value, str):
        redacted = redact_text(value)
        return redacted[:limit] if limit is not None else redacted
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY_PATTERN.search(key_text):
                result[key_text] = "***" if item is not None else None
            else:
                result[key_text] = redact_value(item, limit=limit)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_value(item, limit=limit) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_value(str(value), limit=limit)


def summarize_args(tool: str, args: Any) -> dict[str, Any]:
    """Return audit-safe arguments without file contents or secrets."""
    if not isinstance(args, dict):
        return {"value": redact_value(args)}

    if tool == "execute":
        return {"command": redact_text(str(args.get("command", "")))}
    if tool == "write_file":
        return {
            "file_path": redact_text(str(args.get("file_path", ""))),
            "content_bytes": utf8_len(args.get("content")),
        }
    if tool == "edit_file":
        return {
            "file_path": redact_text(str(args.get("file_path", ""))),
            "old_bytes": utf8_len(args.get("old_string")),
            "new_bytes": utf8_len(args.get("new_string")),
            "replace_all": bool(args.get("replace_all", False)),
        }
    if tool == "delete":
        return {"file_path": redact_text(str(args.get("file_path", "")))}

    summarized: dict[str, Any] = {}
    for key, value in args.items():
        key_text = str(key)
        if _SENSITIVE_KEY_PATTERN.search(key_text):
            summarized[key_text] = "***" if value is not None else None
        else:
            summarized[key_text] = redact_value(value, limit=200)
    return summarized


def display_args(tool: str, args: Any) -> dict[str, Any]:
    """Return redacted arguments with a short content preview for approval UI."""
    summarized = summarize_args(tool, args)
    if isinstance(args, dict) and tool in {"write_file", "edit_file"}:
        content = args.get("content")
        if content is None:
            content = args.get("new_string")
        if isinstance(content, str):
            safe_content = redact_text(content)
            preview = safe_content[:200]
            if len(content) > 200:
                preview += "..."
            summarized["content_preview"] = preview
    return summarized
