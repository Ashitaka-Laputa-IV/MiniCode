"""Append-only JSONL audit log for permission decisions."""

from __future__ import annotations

import getpass
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .redaction import redact_value


class AuditLogger:
    """Write redacted JSONL records to a local audit file."""

    def __init__(
        self,
        path: str | Path,
        *,
        session_id: str,
        mode: str,
        actor: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.session_id = session_id
        self.mode = mode
        try:
            self.actor = actor or getpass.getuser() or "local-user"
        except (OSError, KeyError):
            self.actor = actor or "local-user"
        self._lock = threading.Lock()
        self._warned = False

    def log(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": event,
            "session": self.session_id,
            "mode": self.mode,
            "actor": self.actor,
            **fields,
        }
        safe = redact_value(record)
        line = json.dumps(safe, ensure_ascii=False, default=str)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._lock:
                fd = os.open(
                    self.path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                if os.name != "nt":
                    os.chmod(self.path, 0o600)
        except (OSError, ValueError) as exc:
            if not self._warned:
                print(f"minicode: audit log unavailable: {exc}", file=sys.stderr)
                self._warned = True
