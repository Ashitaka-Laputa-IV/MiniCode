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


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        (".env ", "protected path"),
        (".env.", "protected path"),
        (".env...", "protected path"),
        (".git.", "protected path"),
        (".git ./config", "protected path"),
        (".git./config", "protected path"),
        ("sub/.git./config", "protected path"),
        ("sub/.env /x", "protected path"),
        (".env::$DATA", "invalid or escaping"),
        (".env:stream", "invalid or escaping"),
        ("ENV~1", "invalid or escaping"),
        ("//server/share/.env", "invalid or escaping"),
    ],
)
def test_windows_protected_path_spellings_are_rejected(path: str, reason: str) -> None:
    decision, message = decide({"name": "write_file", "args": {"file_path": path}})

    assert decision == "reject"
    assert reason in message


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
        "mkdir -p build",
        "touch -c marker",
        r"cp notes\todo.md notes\copy.md",
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


@pytest.mark.parametrize(
    "command",
    [
        "pytest\nwhoami",
        "pytest\rwhoami",
        "pytest\ncat .env",
        "pytest -k ^test",
        "pytest -k 'foo!bar'",
    ],
)
def test_newline_command_injection_is_rejected(command: str) -> None:
    decision, reason = decide({"name": "execute", "args": {"command": command}})

    assert decision == "reject"
    assert "allow-list" in reason


@pytest.mark.parametrize(
    "command",
    [
        "cp .env leaked",
        "touch .env",
        "mv x .git/config",
        "mkdir .git",
        "cp ../outside.txt copied.txt",
        "cp /tmp/outside.txt copied.txt",
        "cp $HOME/.env leaked",
        "cp --target-directory=.git x",
        "mkdir -- .git",
        "cp -t/tmp/out x",
        "cp -t.. x",
        "cp -t .git x",
        "cp .env* leaked",
        "cp -r .* leaked",
        "cp -r .[e]nv leaked",
        "mv -t../outside x",
        "touch -r.env x",
        r"mkdir C:\foo",
        r"mkdir ..\outside",
        "cp -r a.py b.py",
        "cp -R a.py b.py",
        "cp -a a.py b.py",
        "cp --archive a.py b.py",
        "cp --arch a.py b.py",
        "cp --recursive a.py b.py",
        "cp --recurs a.py b.py",
        "cp --dereference link dest",
        "cp --deref link dest",
        "cp --no-dereference link dest",
        "cp --no-deref link dest",
        "cp --symbolic-link target dest",
        "cp --sym target dest",
        "cp --link target dest",
        "cp --lin target dest",
        "mv --recursive a.py b.py",
        "mv --recurs a.py b.py",
        "mv --dereference link dest",
        "cp -L link dest",
        "cp -H link dest",
        "cp -P link dest",
        "cp -d link dest",
        "cp -l link dest",
        "cp -s link dest",
        "mkdir ^.git",
        "mkdir .git^",
        "mkdir .env^",
        "mkdir .git.",
        "mkdir .env ",
        "mkdir ENV~1",
        "mkdir .env::$DATA",
        "mkdir .git./config",
        "mkdir .git /config",
        "mkdir .env...",
        "touch .env.",
        "cp .env. leaked",
        "cp ENV~1 leaked",
    ],
)
def test_file_commands_cannot_touch_protected_or_absolute_paths(command: str) -> None:
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
