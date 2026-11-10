import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from minicode.audit import AuditLogger
from minicode.backends import PolicyShellBackend
from minicode.cli import ask_approval
from minicode.policy import PermissionMode, Policy


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def make_audit(tmp_path: Path, mode: str = "ask") -> tuple[AuditLogger, Path]:
    path = tmp_path / "logs" / "audit.jsonl"
    return AuditLogger(path, session_id="session-1", mode=mode, actor="tester"), path


def test_audit_logger_creates_jsonl_with_common_fields(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path)

    audit.log("policy", tool="execute", decision="deny", reason="blocked")

    events = read_events(path)
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "policy"
    assert event["session"] == "session-1"
    assert event["mode"] == "ask"
    assert event["actor"] == "tester"
    assert event["tool"] == "execute"
    assert event["decision"] == "deny"
    assert event["reason"] == "blocked"
    assert event["ts"]


def test_audit_logger_appends_events(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path)

    audit.log("policy", tool="execute", decision="allow")
    audit.log("result", tool="execute", ok=True)

    assert [event["event"] for event in read_events(path)] == ["policy", "result"]


def test_audit_logger_warns_once_when_unavailable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    audit = AuditLogger(blocker / "audit.jsonl", session_id="s", mode="ask")

    audit.log("policy", tool="execute")
    audit.log("result", tool="execute")

    captured = capsys.readouterr()
    assert captured.err.count("audit log unavailable") == 1


def test_read_only_write_logs_deny_and_result(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path, mode="read-only")
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
        audit=audit,
    )
    content = "sk-abcdefghijklmnopqrstuvwxyz"

    result = backend.write("blocked.txt", content)

    assert result.error and "writes are disabled" in result.error
    events = read_events(path)
    assert [event["event"] for event in events] == ["policy", "result"]
    assert events[0]["decision"] == "deny"
    assert events[0]["tool"] == "write_file"
    assert events[0]["args"]["content_bytes"] == len(content)
    assert events[1]["ok"] is False
    assert "sk-" not in path.read_text(encoding="utf-8")


def test_read_only_edit_and_delete_log_denials(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path, mode="read-only")
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
        audit=audit,
    )

    backend.edit("blocked.txt", "old", "new")
    backend.delete("blocked.txt")

    events = read_events(path)
    assert [event["event"] for event in events] == [
        "policy",
        "result",
        "policy",
        "result",
    ]
    assert [event["tool"] for event in events] == [
        "edit_file",
        "edit_file",
        "delete",
        "delete",
    ]
    assert all(event.get("decision", "deny") == "deny" for event in events if "decision" in event)


def test_yolo_hard_deny_logs_reason_and_exit_code(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path, mode="yolo")
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.YOLO),
        audit=audit,
    )

    result = backend.execute("rm -rf /")

    assert result.exit_code == 126
    events = read_events(path)
    assert [event["event"] for event in events] == ["policy", "result"]
    assert events[0]["decision"] == "deny"
    assert "hard deny-list" in events[0]["reason"]
    assert events[1]["ok"] is False
    assert events[1]["exit_code"] == 126


def test_allowed_command_logs_policy_and_result(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path, mode="read-only")
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
        audit=audit,
    )

    result = backend.execute("cd .")

    assert result.exit_code == 0
    events = read_events(path)
    assert events[0]["event"] == "policy"
    assert events[0]["decision"] == "allow"
    assert events[1]["event"] == "result"
    assert events[1]["ok"] is True


def test_ask_approval_logs_approver_and_redacted_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit, path = make_audit(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(Console, "input", lambda self, prompt="": "y")
    monkeypatch.setattr("minicode.cli.approver_name", lambda: "tester")
    interrupt = SimpleNamespace(
        value={
            "action_requests": [
                {
                    "name": "execute",
                    "args": {"command": "curl -H 'Authorization: Bearer abcdefghijklmnop'"},
                }
            ]
        }
    )
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)

    decisions = ask_approval(interrupt, progress, audit)

    assert decisions == [{"type": "approve"}]
    events = read_events(path)
    assert len(events) == 1
    assert events[0]["event"] == "approval"
    assert events[0]["decision"] == "approve"
    assert events[0]["approver"] == "tester"
    assert "abcdefghijklmnop" not in path.read_text(encoding="utf-8")


def test_ask_approval_logs_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit, path = make_audit(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(Console, "input", lambda self, prompt="": "n")
    monkeypatch.setattr("minicode.cli.approver_name", lambda: "tester")
    interrupt = SimpleNamespace(
        value={"action_requests": [{"name": "write_file", "args": {"file_path": "/x"}}]}
    )
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)

    decisions = ask_approval(interrupt, progress, audit)

    assert decisions[0]["type"] == "reject"
    event = read_events(path)[0]
    assert event["decision"] == "reject"
    assert event["approver"] == "tester"
    assert event["reason"] == "user rejected"


def test_ask_approval_non_tty_logs_null_approver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit, path = make_audit(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    interrupt = SimpleNamespace(
        value={"action_requests": [{"name": "execute", "args": {"command": "echo hi"}}]}
    )
    progress = Console(file=io.StringIO(), force_terminal=False, soft_wrap=True)

    decisions = ask_approval(interrupt, progress, audit)

    assert decisions[0]["type"] == "reject"
    event = read_events(path)[0]
    assert event["decision"] == "reject"
    assert event["approver"] is None
    assert event["reason"] == "stdin is not a TTY"


def test_audit_events_share_session_and_mode(tmp_path: Path) -> None:
    audit, path = make_audit(tmp_path)
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.YOLO),
        audit=audit,
    )

    backend.execute("rm -rf /")

    events = read_events(path)
    assert {event["session"] for event in events} == {"session-1"}
    assert {event["mode"] for event in events} == {"ask"}
