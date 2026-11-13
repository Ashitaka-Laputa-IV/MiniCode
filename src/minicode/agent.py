from __future__ import annotations

import os
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from langchain.agents.middleware import InterruptOnConfig
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from .backends import PolicyShellBackend
from .policy import PermissionMode, Policy

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

DEFAULT_MODEL = "deepseek:deepseek-flash"
DEFAULT_CHECKPOINT_DB = Path(".minicode") / "checkpoints.sqlite"

ModelInput = str | BaseChatModel | None

SHELL_ENV_ALLOWLIST = {
    "ALLUSERSPROFILE",
    "APPDATA",
    "COMSPEC",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "LOGONSERVER",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "SESSIONNAME",
    "SSH_AUTH_SOCK",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "USERDOMAIN",
    "USERNAME",
    "USERPROFILE",
    "UV_CACHE_DIR",
    "UV_PROJECT_ENVIRONMENT",
    "VIRTUAL_ENV",
    "WINDIR",
}

SYSTEM_PROMPT = """\
You are MiniCode, a coding agent.

File tools use a virtual filesystem: `/` is the workspace root. Use virtual
paths such as `/src/minicode/cli.py`. Never use Windows drive paths like
`C:\\...` with file tools.

Shell commands run with the workspace as the current directory. Use relative
paths for shell commands. {shell}

Read files before changing them. Make focused changes. Run the project's tests,
lint, or build commands when they exist.

Destructive and irreversible shell commands run without confirmation. Only run
them when the user explicitly asks. When finished, summarize what changed and
what you verified.
"""


def shell_hint() -> str:
    if os.name == "nt":
        return (
            "On Windows the shell is cmd.exe: use cmd syntax and %VAR% expansion, "
            "not POSIX sh syntax."
        )
    return "The shell is POSIX sh: use POSIX syntax and $VAR expansion."


def resolve_model(model: str | None = None) -> str:
    return (model or "").strip() or os.getenv("MINICODE_MODEL", "").strip() or DEFAULT_MODEL


def resolve_root(root: str | Path | None = None) -> Path:
    path = Path(root or Path.cwd()).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"workspace root is not a directory: {path}")
    return path


def shell_env() -> dict[str, str]:
    """Return only the environment variables needed to run shell commands."""
    return {key: value for key, value in os.environ.items() if key.upper() in SHELL_ENV_ALLOWLIST}


def resolve_db_path(root: Path, db_path: str | Path | None = None) -> Path:
    if db_path is not None and str(db_path) == ":memory:":
        raise ValueError("db_path does not support :memory:; use a file path")
    path = Path(db_path).expanduser() if db_path else root / DEFAULT_CHECKPOINT_DB
    if not path.is_absolute():
        path = root / path
    return path


def build_checkpointer(root: Path, db_path: str | Path | None = None) -> SqliteSaver:
    path = resolve_db_path(root, db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn)


def close_checkpointer(agent: "CompiledStateGraph") -> None:
    checkpointer = getattr(agent, "checkpointer", None)
    conn = getattr(checkpointer, "conn", None)
    if conn is not None:
        with suppress(Exception):
            conn.close()


def build_agent(
    *,
    model: ModelInput = None,
    root: str | Path | None = None,
    debug: bool = False,
    checkpoint: bool = False,
    db_path: str | Path | None = None,
    permission_mode: str | PermissionMode = PermissionMode.ASK,
    shell_allow_list: str | list[str] | None = None,
    relay: bool = False,
) -> "CompiledStateGraph":
    """Build the minimal Deep Agents coding harness for one workspace.

    When ``checkpoint`` is enabled, the caller owns the SQLite connection;
    close it with :func:`close_checkpointer` when the agent is no longer used.
    """
    root_path = resolve_root(root)
    model_name = model if isinstance(model, BaseChatModel) else resolve_model(model)
    mode = PermissionMode.parse(permission_mode)
    policy = Policy(mode, allow_commands=shell_allow_list)

    backend = PolicyShellBackend(
        root_dir=root_path,
        env=shell_env(),
        inherit_env=False,
        policy=policy,
    )

    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None
    if mode == PermissionMode.ASK:

        def needs_shell_approval(request: Any) -> bool:
            command = request.tool_call.get("args", {}).get("command", "")
            return isinstance(command, str) and policy.needs_approval(command)

        file_gate = InterruptOnConfig(
            allowed_decisions=["approve", "reject"],
            description="File change requires approval",
        )
        interrupt_on = {
            "write_file": file_gate,
            "edit_file": file_gate,
            "delete": file_gate,
            "execute": InterruptOnConfig(
                allowed_decisions=["approve", "reject"],
                description="Shell command requires approval",
                when=needs_shell_approval,
            ),
        }

    checkpointer: SqliteSaver | InMemorySaver | None = None
    if checkpoint:
        checkpointer = build_checkpointer(root_path, db_path)
    elif mode == PermissionMode.ASK:
        checkpointer = InMemorySaver()
    kwargs: dict[str, Any] = {
        "model": model_name,
        "system_prompt": SYSTEM_PROMPT.format(shell=shell_hint()),
        "backend": backend,
        "interrupt_on": interrupt_on,
        "debug": debug,
        "name": "minicode",
        "checkpointer": checkpointer,
    }
    if relay:
        from nemo_relay.integrations.deepagents import add_nemo_relay_integration

        kwargs = add_nemo_relay_integration(kwargs, position="inner")
    try:
        return create_deep_agent(**kwargs)
    except Exception:
        conn = getattr(checkpointer, "conn", None)
        if conn is not None:
            with suppress(Exception):
                conn.close()
        raise
