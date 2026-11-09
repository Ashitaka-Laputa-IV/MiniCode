# MiniCode

[![CI](https://github.com/Ashitaka-Laputa-IV/MiniCode/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/Ashitaka-Laputa-IV/MiniCode/actions/workflows/ci.yml)

Minimal coding agent built on the [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) harness.

It runs a task or an interactive session against a workspace using the harness's filesystem tools, shell execution, planning, and subagents.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- An API key for a LangChain model provider (DeepSeek by default)

## Setup

```bash
uv sync
```

Set a provider key. The default model is `deepseek:deepseek-flash`. Copy the example file and fill in the key:

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

`minicode` loads `.env` from the current directory or a parent directory. Only `MINICODE_MODEL` and known provider API keys are applied; base URL/endpoint variables such as `OPENAI_BASE_URL` are ignored. Existing shell variables take precedence. For Azure, set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_VERSION` in the shell, not in `.env`. You can also export the variable directly:

```bash
export DEEPSEEK_API_KEY="..."
```

`.env` is ignored by git; only `.env.example` is committed.

## Usage

One-shot:

```bash
uv run minicode "explain the repository structure"
uv run minicode --root ../other-project "fix the failing tests"
uv run python -m minicode "summarize AGENTS.md"
```

Interactive REPL (`minicode` with no prompt also starts it on a TTY):

```bash
uv run minicode
uv run minicode -i
uv run minicode -i --thread work --db .minicode/work.sqlite
```

Inside the REPL, use `/help`, `/reset`, `/exit`, or `/quit`. Conversation state
is persisted to SQLite at `<workspace>/.minicode/checkpoints.sqlite` by default.
Use `--db` to choose another database file and `--thread` to choose a
conversation. `/reset` clears the current thread. Failed or interrupted turns
clear it too, so an incomplete node is not resumed on the next turn.

The default thread is `default`. Parallel REPL instances in the same workspace
share that thread and database; run them with distinct `--thread` and `--db`
values to avoid `database is locked` or interleaved checkpoints.

SQLite options only apply to the interactive REPL. The database contains
conversation history and tool output. `.minicode/` and `*.sqlite*` files are
ignored by git; delete the database or use `/reset` to remove the current
conversation.

Use another provider/model with `--model` or `MINICODE_MODEL`:

```bash
uv run minicode --model deepseek:deepseek-reasoner "review this change"
```

Install that provider's integration package first, for example `uv add langchain-anthropic` or `uv add langchain-openai`.

When the selected model emits reasoning, MiniCode prints it to stderr as a dim
`thinking` block before tool calls and the final answer. stdout still contains
only the final answer. Use `--no-thinking` to suppress it.

## Task evals

The `smoke` suite contains 20 offline fixture tasks: bug fixes, test additions,
refactors, cross-file changes, and small engineering changes.

```bash
uv run minicode eval --baseline all --json evals/results/smoke-all.json
```

Latest local run (2026-11-08, `deepseek:deepseek-flash`, one attempt per task):

| baseline | pass@1 | tool calls/task | input/output tokens | cost | wall time |
| --- | ---: | ---: | ---: | ---: | ---: |
| `full` (MiniCode) | 20/20 (100%) | 11.2 | 664,332 / 28,954 | $0.0852 | 585.9s |
| `bare` (model only) | 0/20 (0%) | 0.0 | 1,323 / 10,334 | $0.0117 | 240.1s |

This is a **smoke suite**, not a general coding benchmark. The tasks are small
and selected by the same repository; use the numbers for regression tracking,
not as a claim about arbitrary repositories. Verification isolation is
convention-level: it prevents config-based bypass, but it is not an adversarial
sandbox against a malicious agent.

Task definitions live in `evals/tasks/`, the suite in
`evals/suites/smoke.toml`, and the runner in `src/minicode/evals/`. See
[`evals/README.md`](evals/README.md) for the task format.

## Development

Run the same checks locally that PR CI runs:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q --cov=minicode --cov-report=term-missing
```

Format changed files with `uv run ruff format .`. Coverage must stay at or above
50%; the floor is configured in `pyproject.toml` and should be raised as
coverage improves. New code should come with tests rather than relying on the
floor.

Live tests call a real model and are excluded from the default run:

```bash
uv run pytest -m live -q
```

They require `DEEPSEEK_API_KEY`, currently support DeepSeek models only, and
fail when the key or model is missing. They are never part of PR CI. Use the
**Live tests** workflow in the Actions tab for a manual run.

PR CI runs unit tests and static checks only and never calls a model. Live evals
are manual: use the **Live eval** workflow in the Actions tab (it requires a
`DEEPSEEK_API_KEY` repository secret) or run the commands above locally. See
[`evals/README.md`](evals/README.md) for details and cost notes.

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
