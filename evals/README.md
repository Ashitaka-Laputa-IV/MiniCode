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
```

`full` runs MiniCode. `bare` sends the same prompt directly to the model with
no tools. `all` runs both baselines. A bare-only run is informational and exits
0 even when tasks fail; `full` failures still exit 1.

Reports are written only when `--json` is passed. `evals/results/` is ignored by
git.

The eval worker runs in a non-interactive subprocess, so it explicitly uses
`permission_mode="yolo"`. Fixtures are copied to temporary directories, and the
shell hard deny-list still applies, but this is not a sandbox.

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

- `pass_at_1`: one attempt per task, passed / total
- `tool_calls`: count of model tool calls
- `input_tokens` / `output_tokens`: summed provider usage
- `cost_usd`: computed from `evals/pricing.toml`
- `duration_s`: wall-clock time per task

Update `pricing.toml` when provider prices change.

## CI

PR CI runs unit tests and static checks only; it never calls a model. The
**Live eval** GitHub Actions workflow is manual (`workflow_dispatch`) and
requires the `DEEPSEEK_API_KEY` repository secret. It uploads the JSON report as
an artifact. Live evals cost money and take several minutes, so do not add them
to pull request checks.

## Adding a task

1. Create `evals/tasks/<id>/fixture/` with a minimal failing repository.
2. Write `prompt.md` with an unambiguous requirement.
3. Add `hidden/test_hidden.py` when verification should be hidden.
4. Add an explicit `verify.py` when the check is not just "pytest passes".
5. Add the task id to `evals/suites/smoke.toml`.
6. Run it with `--task <id>` before adding it to the suite.

Keep tasks small and deterministic. Do not depend on the network from fixture
tests; model calls are the only network dependency.
