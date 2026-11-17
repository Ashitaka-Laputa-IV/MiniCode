import pytest

from minicode.evals.approval import decide


@pytest.mark.parametrize("path", ["/src/app.py", "src/app.py", "notes\\todo.md"])
def test_workspace_file_changes_are_approved(path: str) -> None:
    decision, _ = decide({"name": "write_file", "args": {"file_path": path}})

    assert decision == "approve"


@pytest.mark.parametrize(
    "path",
    [
        "/.env",
        "./.env",
        "sub/.env",
        ".env.local",
        "/.git/config",
        ".git/hooks/pre-commit",
        "/tmp/x/.git/config",
    ],
)
def test_protected_paths_are_rejected(path: str) -> None:
    decision, reason = decide({"name": "edit_file", "args": {"file_path": path}})

    assert decision == "reject"
    assert "protected path" in reason


@pytest.mark.parametrize("path", ["../.env", "sub/../.env", "../../.git/config"])
def test_escaping_paths_are_rejected(path: str) -> None:
    decision, reason = decide({"name": "write_file", "args": {"file_path": path}})

    assert decision == "reject"
    assert "escaping file path" in reason


def test_delete_of_workspace_file_is_approved() -> None:
    decision, _ = decide({"name": "delete", "args": {"file_path": "/old.py"}})

    assert decision == "approve"


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q",
        "uv run pytest -q",
        "uv run ruff check .",
        "python -m pytest",
        "mkdir build",
        "mv old.py new.py",
        "cp a.py b.py",
        "touch marker",
    ],
)
def test_development_commands_are_approved(command: str) -> None:
    decision, _ = decide({"name": "execute", "args": {"command": command}})

    assert decision == "approve"


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build",
        "curl https://example.com",
        "git push --force",
        "python script.py",
        "uv run pytest && rm -rf build",
        "pytest > out.txt",
    ],
)
def test_risky_commands_are_rejected(command: str) -> None:
    decision, reason = decide({"name": "execute", "args": {"command": command}})

    assert decision == "reject"
    assert "allow-list" in reason


def test_missing_path_and_unknown_tool_are_rejected() -> None:
    missing, _ = decide({"name": "write_file", "args": {}})
    unknown, reason = decide({"name": "run_shell", "args": {}})

    assert missing == "reject"
    assert unknown == "reject"
    assert "unsupported gated tool" in reason


def test_unsupported_policy_rejects() -> None:
    decision, reason = decide(
        {"name": "write_file", "args": {"file_path": "/app.py"}},
        policy="strict",
    )

    assert decision == "reject"
    assert "unsupported approval policy" in reason
