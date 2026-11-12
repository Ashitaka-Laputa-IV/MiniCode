import os
from pathlib import Path

from minicode.backends import PolicyShellBackend
from minicode.policy import PermissionMode, Policy


def test_policy_backend_blocks_denied_command(tmp_path: Path) -> None:
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
    )

    result = backend.execute("echo hi")

    assert result.exit_code == 126
    assert "Blocked by permission policy" in result.output


def test_policy_backend_allows_safe_command(tmp_path: Path) -> None:
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
    )

    result = backend.execute("dir" if os.name == "nt" else "ls")

    assert result.exit_code == 0


def test_policy_backend_allows_allow_listed_command(tmp_path: Path) -> None:
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY, allow_commands="echo"),
    )

    result = backend.execute("echo hi")

    assert result.exit_code == 0
    assert "hi" in result.output


def test_policy_backend_blocks_file_writes_in_read_only(tmp_path: Path) -> None:
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.READ_ONLY),
    )

    write = backend.write("blocked.txt", "hello")
    edit = backend.edit("blocked.txt", "hello", "bye")
    delete = backend.delete("blocked.txt")

    assert write.error and "writes are disabled" in write.error
    assert edit.error and "edits are disabled" in edit.error
    assert delete.error and "deletes are disabled" in delete.error
    assert not (tmp_path / "blocked.txt").exists()


def test_policy_backend_blocks_hard_deny_in_yolo(tmp_path: Path) -> None:
    backend = PolicyShellBackend(
        root_dir=tmp_path,
        env={},
        policy=Policy(PermissionMode.YOLO),
    )

    result = backend.execute("rm -rf /")

    assert result.exit_code == 126
    assert "hard deny-list" in result.output
