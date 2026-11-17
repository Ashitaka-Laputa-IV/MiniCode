"""Structured traces for evaluation runs.

Traces are evaluation-only data. They are written to a temporary work directory
and are not part of the production audit surface.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

TEST_COMMAND_MARKERS = (
    "pytest",
    "unittest",
    "npm test",
    "cargo test",
    "go test",
)


@dataclass(frozen=True)
class TraceEvent:
    type: str
    time: float
    data: dict[str, Any]


def _signature(name: str, args: Any) -> str:
    serialized = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return f"{name}:{serialized}"


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
            command = str(args.get("command", "")).lower()
            if any(marker in command for marker in TEST_COMMAND_MARKERS):
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
    """Read a JSONL trace, returning an empty list when the file is absent."""
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    events: list[TraceEvent] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        events.append(
            TraceEvent(
                type=str(payload.get("type", "")),
                time=float(payload.get("time", 0.0)),
                data=dict(payload.get("data", {})),
            )
        )
    return events
