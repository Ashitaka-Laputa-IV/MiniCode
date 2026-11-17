"""Structured traces for evaluation runs.

Traces are evaluation-only data. They are written to a temporary work directory
and are not part of the production audit surface.
"""

from __future__ import annotations

import json
import re
import shlex
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

TEST_RUNNERS = {"pytest", "py.test", "tox", "nox"}
TEST_MODULES = {"pytest", "unittest"}
TEST_FLAGS_WITHOUT_TESTS = {
    "--version",
    "--help",
    "--collect-only",
    "--co",
    "-V",
    "-h",
}


@dataclass(frozen=True)
class TraceEvent:
    type: str
    time: float
    data: dict[str, Any]


def _signature(name: str, args: Any) -> str:
    serialized = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return f"{name}:{serialized}"


def _is_test_command(command: str) -> bool:
    """Return true only when the command actually invokes a test runner."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False

    lowered = [token.lower() for token in tokens]
    index = 0
    while index < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index]):
        index += 1
    if lowered[index : index + 2] == ["uv", "run"]:
        index += 2
    if index >= len(tokens):
        return False

    first = lowered[index]
    if first in TEST_RUNNERS:
        return not any(token in TEST_FLAGS_WITHOUT_TESTS for token in tokens[index + 1 :])
    if first in {"python", "python3", "py"}:
        if index + 2 >= len(tokens) or lowered[index + 1] != "-m":
            return False
        if lowered[index + 2] not in TEST_MODULES:
            return False
        return not any(token in TEST_FLAGS_WITHOUT_TESTS for token in tokens[index + 3 :])
    if lowered[index : index + 2] == ["npm", "test"]:
        return True
    if lowered[index : index + 3] == ["npm", "run", "test"]:
        return True
    if lowered[index : index + 2] == ["cargo", "test"]:
        return "--no-run" not in tokens[index + 2 :]
    if lowered[index : index + 2] in (["go", "test"], ["make", "test"]):
        return True
    return False


class Trace:
    """Collect trace events and optionally append them to a JSONL file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.events: list[TraceEvent] = []
        self._file: TextIO | None = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8")

    def record(self, event_type: str, **data: Any) -> None:
        event = TraceEvent(type=event_type, time=time.time(), data=data)
        self.events.append(event)
        if self._file is not None:
            payload = {"type": event_type, "time": event.time, "data": data}
            self._file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._file.flush()

    def sink(self, event_type: str, data: dict[str, Any]) -> None:
        """Adapter for callbacks that take a single data mapping."""
        self.record(event_type, **data)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> Trace:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def summary(self) -> dict[str, Any]:
        return summarize_events(self.events)


def summarize_events(events: list[TraceEvent]) -> dict[str, Any]:
    """Summarize trace events, including partial usage from interrupted runs."""
    tool_calls = [event.data for event in events if event.type == "tool_call"]
    approvals = [
        event.data
        for event in events
        if event.type == "approval" and event.data.get("decision") == "approve"
    ]
    rejections = [
        event.data
        for event in events
        if event.type == "approval" and event.data.get("decision") == "reject"
    ]
    denials = [
        event.data
        for event in events
        if event.type == "policy_decision" and event.data.get("action") == "DENY"
    ]

    signatures: dict[str, int] = {}
    touched_paths: list[str] = []
    ran_tests = False
    for call in tool_calls:
        name = str(call.get("name", ""))
        args = call.get("args", {})
        signature = _signature(name, args)
        signatures[signature] = signatures.get(signature, 0) + 1
        if name == "execute" and isinstance(args, dict):
            command = str(args.get("command", ""))
            if _is_test_command(command):
                ran_tests = True
        if name in {"write_file", "edit_file", "delete"} and isinstance(args, dict):
            path = args.get("file_path") or args.get("path")
            if path:
                touched_paths.append(str(path))

    usage: dict[str, int] = {}
    for event in events:
        if event.type != "usage":
            continue
        for key, value in event.data.items():
            if key in {"input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"}:
                if isinstance(value, (int, float)):
                    usage[key] = usage.get(key, 0) + int(value)

    denial_reasons = Counter(str(event.get("reason", "")) for event in denials)
    return {
        "events": len(events),
        "tool_calls": len(tool_calls),
        "approvals": len(approvals),
        "rejections": len(rejections),
        "blocked": len(denials),
        "ran_tests": ran_tests,
        "repeated_tool_calls": any(count >= 3 for count in signatures.values()),
        "denial_reasons": dict(sorted(denial_reasons.items())),
        "touched_paths": list(dict.fromkeys(touched_paths)),
        "usage": usage,
    }


def read_trace(path: str | Path) -> list[TraceEvent]:
    """Read a JSONL trace, tolerating a missing or truncated final line."""
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    try:
        payload_bytes = trace_path.read_bytes()
    except OSError:
        return []
    text = payload_bytes.decode("utf-8", errors="replace")
    events: list[TraceEvent] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            data = payload.get("data", {})
            events.append(
                TraceEvent(
                    type=str(payload.get("type", "")),
                    time=float(payload.get("time", 0.0)),
                    data=dict(data) if isinstance(data, dict) else {},
                )
            )
        except (TypeError, ValueError):
            # A killed worker can leave a partial JSON line; keep earlier events.
            continue
    return events
