# Held-out eval results: 2026-11-18

This report records the first full run of the 20-task held-out suite on `opencode-go:deepseek-v4.1-flash`. It is a regression signal, not a general coding benchmark. The suite contains 11 Python and 9 JavaScript tasks across bugfix, cross-file, add-tests, and refactor categories.

## Metadata

- Date: 2026-11-18
- Evaluated commit: `a88f660a80fcfa259dc5dd68e2029cdf218700eb` (merge of the expanded held-out suite)
- Model: `opencode-go:deepseek-v4.1-flash`
- Suite: `evals/suites/heldout.toml` (20 tasks)
- Runs: `minicode-yolo` used two attempts per task; the other three baselines used one attempt, so their pass@k cells are `n/a`.
- Totals: 100 task runs, $0.1424 estimated cost, 4,485.4s summed worker wall time (jobs overlapped, so this is not elapsed clock time).

Reproduce:

```bash
uv run minicode eval --suite heldout --baseline minicode-yolo \
  --model opencode-go:deepseek-v4.1-flash --runs 2 --json evals/results/issue36-heldout-yolo-runs2.json
uv run minicode eval --suite heldout --baseline minicode-ask \
  --model opencode-go:deepseek-v4.1-flash --runs 1 --json evals/results/issue36-heldout-ask-runs1.json
uv run minicode eval --suite heldout --baseline minicode-no-subagents \
  --model opencode-go:deepseek-v4.1-flash --runs 1 --json evals/results/issue36-heldout-nosub-runs1.json
uv run minicode eval --suite heldout --baseline deepagents-default \
  --model opencode-go:deepseek-v4.1-flash --runs 1 --json evals/results/issue36-heldout-deepagents-runs1.json
```

## Results

| Baseline | Passed / task runs | pass@1 | pass@k | Avg tool calls | Approvals / run | Blocked / run | Input tokens | Output tokens | Cost | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `minicode-yolo` | 40 / 40 | 100.0% | 100.0% | 10.85 | 0.00 | 0.00 | 1,179,511 | 56,030 | $0.0488 | 1,061.8s |
| `minicode-ask` | 20 / 20 | 100.0% | n/a | 11.35 | 2.70 | 0.00 | 627,006 | 32,022 | $0.0267 | 889.5s |
| `minicode-no-subagents` | 20 / 20 | 100.0% | n/a | 11.30 | 0.00 | 0.00 | 583,596 | 30,582 | $0.0261 | 923.4s |
| `deepagents-default` | 14 / 20 | 70.0% | n/a | 17.10 | 0.00 | 0.00 | 1,122,400 | 42,996 | $0.0409 | 1,610.8s |

`minicode-yolo` used two attempts per task, so its pass@k is estimated from two attempts. The other three baselines used one attempt; their pass@k cells are `n/a` rather than copying pass@1.

`deepagents-default` passed 14/20 task runs with 17.10 tool calls per run; failures were `timeout`=2, `tool_limit`=4.

The MiniCode baselines were at or near the ceiling on this suite; the native Deep Agents baseline spent more calls per task and hit the fixture limits on several tasks. See the failure analysis below.

## Task-level pass counts

| Task | yolo | ask | no-subagents | deepagents |
|---|---:|---:|---:|---:|
| `heldout-js-add-tests-slug` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-js-cross-file-cart` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-js-cross-file-greeting` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-js-fix-binary-search` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-js-fix-pagination` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-js-refactor-config` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-js-refactor-errors` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-js-refactor-format` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-js-refactor-validation` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-add-tests-csv` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-cross-file-discount` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-cross-file-settings` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-cross-file-shipping` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-fix-chunk` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-py-fix-duration` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-py-fix-merge-intervals` | 2/2 | 1/1 | 1/1 | 0/1 |
| `heldout-py-refactor-normalize` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-refactor-rate` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-py-regression-tests` | 2/2 | 1/1 | 1/1 | 1/1 |
| `heldout-real-requests-link-header` | 2/2 | 1/1 | 1/1 | 1/1 |

## Failure analysis

There were 6 failed task runs. The table below lists every failure; representative cases are discussed afterward.

| Baseline | Task | Run | Failure category |
|---|---|---:|---|
| `deepagents-default` | `heldout-py-fix-chunk` | 1 | `tool_limit` |
| `deepagents-default` | `heldout-py-fix-duration` | 1 | `tool_limit` |
| `deepagents-default` | `heldout-py-fix-merge-intervals` | 1 | `tool_limit` |
| `deepagents-default` | `heldout-js-cross-file-greeting` | 1 | `tool_limit` |
| `deepagents-default` | `heldout-js-cross-file-cart` | 1 | `timeout` |
| `deepagents-default` | `heldout-js-refactor-config` | 1 | `timeout` |

### 1. `heldout-py-fix-chunk` (deepagents-default, run 1)

Category `tool_limit`: worker hit the per-task tool-call limit. The run used 21 tool calls and 66.5s.

```text
RuntimeError: tool call limit exceeded: 20
```

### 2. `heldout-js-cross-file-cart` (deepagents-default, run 1)

Category `timeout`: worker exceeded the per-task agent timeout. The run used 13 tool calls and 180.0s.

```text
task timed out after 180s
```

### 3. `heldout-py-fix-duration` (deepagents-default, run 1)

Category `tool_limit`: worker hit the per-task tool-call limit. The run used 21 tool calls and 83.7s.

```text
RuntimeError: tool call limit exceeded: 20
```

## Real-repository case study

The suite includes one minimized real-repository fixture from `psf/requests` v2.4.3 (`parse_header_links`, upstream issue #2250, fix PR #2271). A separate case study documents a `minicode-ask` run with six approval interrupts, one rejected command, a retry, and a final `3 passed`: [`case-study-requests.md`](case-study-requests.md).

## Limitations

- Twenty tasks are a small, curated sample. The results are not a SWE-bench-style ranking and should not be presented as state-of-the-art.
- All three MiniCode baselines passed every task run, so this run cannot separate them; the suite has a ceiling effect for current MiniCode on these tasks.
- The fixtures are deterministic and mostly hand-authored; they emphasize specific editing patterns rather than the full distribution of repository work.
- `deepagents-default` has one attempt per task, so its pass@1 has wider uncertainty and no pass@k estimate.
- The eval approver used by `minicode-ask` is a deterministic cooperative policy, not a human reviewer or a sandbox.
- Raw JSON and logs are release assets, not committed files. `evals/results/` remains ignored.

## Artifacts

- Release: [`heldout-results-2026-11-18`](https://github.com/Ashitaka-Laputa-IV/MiniCode/releases/tag/heldout-results-2026-11-18)
- Issue: [issue #36](https://github.com/Ashitaka-Laputa-IV/MiniCode/issues/36)
- Raw result files: `issue36-heldout-*.json` and `.log` in the release zip

The result JSON records per-task pass counts, failure categories, usage, cost, and wall time. Re-running with a different model or date should use a new report rather than overwriting this one.
