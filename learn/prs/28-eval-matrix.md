# PR #28：把评测从“跑一遍”变成 baseline 矩阵

一句话：这个 PR 让评测可以同时比较多种配置，重复跑多次算 pass@k，并且把工具调用、审批、拒绝和失败原因记录下来。

## 之前缺什么

原来的评测只有 `full` 和 `bare` 两个口径，每个任务跑一次。它能回答“agent 有没有把 fixture 改对”，但回答不了这些问题：

- 关掉 checkpoint 会差多少？
- `ask` 模式经过 HITL 之后，通过率变不变？
- 原生 Deep Agents 没有 MiniCode 的 `Policy` 和提示，结果差在哪？
- 同一次任务多跑几次，是稳定通过还是碰巧通过？

没有 baseline 注册表，这些比较只能靠人手工改参数；没有 trace，审批和拒绝只留在终端输出里，报告无法聚合。

## 改了什么

### baseline 变成一等对象

`src/minicode/evals/baselines.py` 定义了 `Baseline` 和 `BASELINES`（[`baselines.py#L20`](../../src/minicode/evals/baselines.py#L20)）。每个 baseline 说明自己用哪种权限模式、开不开 checkpoint、走不走 MiniCode 的包装。`full` 保留为 `minicode-yolo` 的别名，`all` 仍然是 `full + bare`，`matrix` 展开成当前矩阵。

PR #28 先放了五个 baseline：`bare`、`deepagents-default`、`minicode-yolo`、`minicode-ask`、`minicode-no-checkpoint`。`minicode-no-subagents` 是后面的 #29 加的第六个。

### `--runs` 和 pass@k

`--runs N` 会让每个任务在每个选中的 baseline 里重复跑 N 次。`pass@k` 的 `k` 就是 `runs`，计算方式是“每个任务在 k 次里至少通过一次”的比例（[`classify.py#L107`](../../src/minicode/evals/classify.py#L107)）。默认 `runs=1`，小于 1 会被拒绝。

这比“把所有 run 的通过数直接平均”更接近你要问的问题：一个任务多试几次能不能过。报告里同时保留 `pass_at_1` 和 `pass_at_k`，以及每个任务的通过次数。

### `minicode-ask` 需要一个非交互审批人

评测 worker 是子进程，没有 stdin 可以等人按 y。`src/minicode/evals/approval.py` 提供了一个确定性的脚本审批器 `decide()`（[`approval.py#L222`](../../src/minicode/evals/approval.py#L222)）。

它批准普通的 workspace 文件修改，以及一小段开发命令：`pytest`、`uv run pytest`、`ruff`、`python -m pytest`、`mkdir`、`mv`、`cp`、`touch`。它会拒绝 `.git/` 和 `.env` 这类受保护路径，也会处理 Windows 的 ADS、8.3 短名、尾点和尾空格写法。`cp` 不允许递归；`mv` 只检查路径 token，移动目录仍可能把受保护文件带进去；这些检查是词法检查，不解析符号链接。

这让 `minicode-ask` 的 HITL 路径能在评测里跑起来，但它是一个“评测用审批人”，不代表默认 CLI 的审批行为。

### trace 和失败分类

`src/minicode/evals/trace.py` 写评测专用的 JSONL。`summarize_events()`（[`trace.py#L118`](../../src/minicode/evals/trace.py#L118)）统计工具调用、批准、拒绝、策略拒绝、是否真的跑了测试、重复调用、拒绝原因、碰过的路径和 token 用量。

`src/minicode/evals/classify.py` 把失败分成确定性的类别：`timeout`、`tool_limit`、`permission_denied`、`agent_error`、`loop`、`no_tests_run`、`context_overflow`、`verification_failed`。分类不是让模型判断，而是根据 worker、verify 和 trace 的证据做规则判断。

worker 被中断、超时或没有返回结果时，runner 会从 trace 文件恢复部分 usage 和计数；最后一行 JSONL 如果被截断，会忽略它。这比报告一堆 0 更接近真实消耗。

## 怎么用

跑当前完整矩阵一次：

```bash
uv run minicode eval --baseline matrix --runs 1 --json evals/results/smoke-matrix.json
```

跑三次看 pass@3：

```bash
uv run minicode eval --baseline matrix --runs 3 --json evals/results/smoke-matrix-3.json
```

只比较 `full` 和 `bare` 时，`--baseline all` 还是原来的意思，不会把六个 baseline 全拉进来。

## 代价和边界

矩阵的模型调用量是“baseline 数 × 任务数 × runs”，很容易变成几分钟到几十分钟，也有真实 API 成本。所以它不在 PR CI 里跑，只在手动 live eval 或改评测 runner 时跑。

评测隔离是约定级的：fixture 复制到临时目录，hidden tests 在 agent 结束后才放进去，shell 环境过滤，但这不是 sandbox。`deepagents-default` 没有 `Policy`，也没有 hard deny，只能当作框架对照，不能当作安全运行时。

## 测试

`tests/test_evals_baselines.py` 检查别名、矩阵展开、去重和未知 baseline；`tests/test_evals_approval.py` 覆盖审批器的允许和拒绝路径；`tests/test_evals.py` 覆盖 pass@k、trace 指标、partial trace 恢复和多 baseline 汇总；`tests/test_evals_cli.py` 覆盖 `--runs` 和 matrix 参数。

## 读完后你应该能回答

1. `full`、`all`、`matrix` 三个词各自展开成什么？
2. `pass@k` 和“把所有 run 的通过率平均”差在哪？
3. 为什么 `minicode-ask` 在评测里需要一个脚本审批器？
4. 为什么 trace 只能在评测里用，不能当生产审计？
