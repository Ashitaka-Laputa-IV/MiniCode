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

Set a provider key. The default model is `deepseek:deepseek-chat`. Copy the example file and fill in the key:

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

`minicode` loads `.env` from the current directory or a parent directory. You can also export the variable directly:

```bash
export DEEPSEEK_API_KEY="..."
```

`.env` is ignored by git; only `.env.example` is committed.

## Usage

```bash
uv run minicode "explain the repository structure"
uv run minicode --root ../other-project "fix the failing tests"
uv run python -m minicode "summarize AGENTS.md"
```

Use another provider/model with `--model` or `MINICODE_MODEL`:

```bash
uv run minicode --model deepseek:deepseek-reasoner "review this change"
```

Install that provider's integration package first, for example `uv add langchain-anthropic` or `uv add langchain-openai`.

## Safety

The agent uses `LocalShellBackend`: it can read and write files and run arbitrary
shell commands with your user permissions. There is no human-in-the-loop
approval loop, so destructive commands can run unattended. Use it only in
workspaces you trust and only for tasks you are willing to let run.

Shell commands receive a filtered environment: common OS/PATH/temp variables
plus Python and uv paths. Provider API keys are not inherited by the agent's
shell commands.

## Project tooling

- OpenCode MCP servers: `docs-langchain`, `reference-langchain` (see `opencode.json`)
- Project skill: `caveman` under `.agents/skills/` (see `AGENTS.md`)
