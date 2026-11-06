from __future__ import annotations

import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend

DEFAULT_MODEL = "deepseek:deepseek-chat"


def resolve_model(model: str | None = None) -> str:
    return model or os.getenv("MINICODE_MODEL", DEFAULT_MODEL)

SYSTEM_PROMPT = """\
You are MiniCode, a coding agent working in: {root}

Use the available filesystem and shell tools to inspect, modify, and verify code.
Read files before changing them. Make focused changes. Run the project's tests,
lint, or build commands when they exist.

Stay inside the workspace. Ask before running destructive or irreversible
commands. When finished, summarize what changed and what you verified.
"""


def build_agent(
    *,
    model: str | None = None,
    root: str | Path | None = None,
    debug: bool = False,
):
    """Build the minimal Deep Agents coding harness for one workspace."""
    root_path = Path(root or Path.cwd()).resolve()
    model_name = resolve_model(model)

    backend = LocalShellBackend(
        root_dir=root_path,
        inherit_env=True,
    )

    return create_deep_agent(
        model=model_name,
        system_prompt=SYSTEM_PROMPT.format(root=root_path),
        backend=backend,
        debug=debug,
        name="minicode",
    )
