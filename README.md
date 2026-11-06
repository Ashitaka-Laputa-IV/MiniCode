# MiniCode

Minimal coding agent built on the [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) harness.

It runs one task against a workspace using the harness's filesystem tools, shell execution, planning, and subagents.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- An API key for a LangChain model provider (DeepSeek by default)

## Setup

```bash
uv sync
```

Set a provider key. The default model is `deepseek:deepseek-chat`:

```bash
export DEEPSEEK_API_KEY="..."
```

PowerShell:

```powershell
$env:DEEPSEEK_API_KEY = "..."
```

## Usage

```bash
uv run minicode "explain the repository structure"
uv run minicode --root ../other-project "fix the failing tests"
uv run python -m minicode "summarize AGENTS.md"
```

Use another provider/model with `--model` or `MINICODE_MODEL`:

```bash
uv run minicode --model anthropic:claude-sonnet-5 "review this change"
```

Install that provider's integration package first, for example `uv add langchain-anthropic` or `uv add langchain-openai`.

## Safety

The agent uses `LocalShellBackend`: it can read and write files and run arbitrary
shell commands with your user permissions. Use it only in workspaces you trust.
The system prompt asks it to stay in the workspace and confirm destructive
commands, but this is not a hard sandbox.

## Project tooling

- OpenCode MCP servers: `docs-langchain`, `reference-langchain` (see `opencode.json`)
- Project skill: `caveman` under `.agents/skills/` (see `AGENTS.md`)
