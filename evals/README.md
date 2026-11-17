# MiniCode task evals

This directory contains the `smoke` suite: 20 small, self-contained tasks used
to answer "does the agent actually change a repository correctly?".

The suite is intentionally small. It is a regression signal, not a claim of
general coding ability.

## Run

```bash
uv run minicode eval --baseline full --json evals/results/smoke-full.json
uv run minicode eval --baseline bare --json evals/results/smoke-bare.json
uv run minicode eval --baseline all --json evals/results/smoke-all.json
uv run minicode eval --baseline matrix --runs 1 --json evals/results/smoke-matrix.json
```

- `full` is the legacy alias for `minicode-yolo`.
- `all` still means `full` + `bare`.
- `matrix` runs the current six-baseline matrix.
- `--runs N` repeats every task in every selected baseline. `pass@k` uses
  `k = runs`; the default is 1.

Reports are written only when `--json` is passed. `evals/results/` is ignored by
git.

## Baselines

| baseline | description |
| --- | --- |
| `bare` | Sends the prompt directly to the model with no tools. Lower bound. |
| `deepagents-default` | Native `create_deep_agent` plus `LocalShellBackend` and the filtered shell environment. No MiniCode system prompt, `Policy`, HITL, or checkpointer. |
| `minicode-yolo` | MiniCode with `yolo` permission mode and checkpointing enabled. |
| `minicode-ask` | MiniCode with `ask` mode, checkpointing enabled, and a scripted non-interactive approver. |
| `minicode-no-checkpoint` | Same as `minicode-yolo` but without a checkpointer. The difference is expected to matter only in recovery runs. |
| `minicode-no-subagents` | Same as `minicode-yolo` but removes the `task` tool and rejects any attempted subagent call. Isolates the contribution of subagents. |

`deepagents-default` has no `PolicyShellBackend`, so it also has no hard
deny-list. Treat it as a framework-level comparison, not a safe runtime.

`minicode-ask` approves ordinary workspace file edits and a small development
command allow-list (`pytest`, `uv run pytest`, `ruff`, `python -m pytest`,
`mkdir`, `mv`, `cp`, `touch`). For gated writes/deletes and direct path-command
arguments it rejects protected paths (`.git/`, `.env`), including Windows
alternate-data-stream, 8.3 short-name, and trailing-dot/space spellings.
Normal Policy read-only commands such as `cat .env` are not reviewed by this
approver. `cp` is non-recursive: recursive flags are rejected. `mv` only checks
the path tokens; moving a directory can move protected files inside it, so use
`mv` for files only. Protected-path checks are lexical; symlinks and existing
file contents are not resolved. This is a deterministic eval user, not a claim
that the default CLI approval flow behaves this way.

The eval worker runs in a non-interactive subprocess, so `minicode-ask` uses the
scripted approver instead of stdin. `deepagents-default` and the yolo baselines
run without HITL. Fixtures are copied to temporary directories, and the shell
hard deny-list still applies to MiniCode baselines, but this is not a sandbox.

## Task layout

```text
evals/tasks/<id>/
  task.toml
  prompt.md
  fixture/
  hidden/            # optional, copied in only after the agent finishes
  verify.py          # alternative to a pytest verification command
```

`task.toml`:

```toml
id = "fix-import"
category = "bugfix"
timeout_seconds = 180            # fallback for both phases
agent_timeout_seconds = 180      # optional
verify_timeout_seconds = 180     # optional
max_tool_calls = 30
hidden_tests = "hidden"          # optional
verify_command = "python -m pytest -q"  # optional; this is the default
# verify_script = "verify.py"    # alternative to verify_command
```

Rules:

- The fixture is copied to a fresh temporary directory for every run.
- Hidden tests are not copied into the workspace during the agent run; they are
  copied to a sibling directory for verification. This is convention-level
  hiding, not sandbox isolation.
- Correctness is based on executable verification, not an LLM judge.
- Verification runs with a filtered environment (`SHELL_ENV_ALLOWLIST`) and
  `PYTHONPATH` pointing at the fixture workspace.
- `bare` does not edit files, so it is useful as a floor baseline.

## Metrics

`report.json` contains per-task results and aggregate metrics:

- `pass_at_1`: pass rate across all runs
- `pass_at_k`: fraction of tasks with at least one pass in `k` runs
- `pass_at_1_std` / `pass_at_k_std`: population standard deviation
- `tool_calls`: count of model tool calls
- `avg_approvals`: average approval events per run
- `avg_blocked`: average policy denials per run
- `failure_counts`: deterministic failure classification counts
- `input_tokens` / `output_tokens`: summed provider usage
- `cost_usd`: computed from `evals/pricing.toml`
- `duration_s`: wall-clock time per task

Failure categories currently include `timeout`, `tool_limit`,
`permission_denied`, `loop`, `no_tests_run`, `context_overflow`,
`verification_failed`, and `agent_error`. `wrong_files` is intentionally not
classified without task-level expected-path metadata; those failures fall back
to `verification_failed`.

MiniCode and `deepagents-default` runs write a temporary `trace.jsonl` next to
their workspace; `bare` runs do not. Traces are for evals only and are kept only
with `--keep`; reports contain summaries, not raw tool output. When a worker is
interrupted, times out, or exits without a result, the runner restores partial
usage and trace counts from the trace file instead of reporting zeroes; a
truncated final JSONL line is ignored. Do not put secrets in fixture files.

Update `pricing.toml` when provider prices change.

## CI

PR CI runs unit tests and static checks only; it never calls a model. The
**Live eval** GitHub Actions workflow is manual (`workflow_dispatch`) and
requires the `DEEPSEEK_API_KEY` repository secret. It can run any single
baseline, `all`, or `matrix`, and accepts a `runs` input for pass@k. It uploads
the JSON report as an artifact. Live evals cost money and take several minutes,
so do not add them to pull request checks.

Security and recovery suites are not part of this PR; they will be added in
separate follow-ups.

## Adding a task

1. Create `evals/tasks/<id>/fixture/` with a minimal failing repository.
2. Write `prompt.md` with an unambiguous requirement.
3. Add `hidden/test_hidden.py` when verification should be hidden.
4. Add an explicit `verify.py` when the check is not just "pytest passes".
5. Add the task id to `evals/suites/smoke.toml`.
6. Run it with `--task <id>` before adding it to the suite.

Keep tasks small and deterministic. Do not depend on the network from fixture
tests; model calls are the only network dependency.
