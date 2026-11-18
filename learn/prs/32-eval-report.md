# PR #32：让评测报告说清楚“为什么没过”

一句话：这个 PR 补了评测报告的指标和失败分类，还加了一个很实用的判断：任务只应该改 `expected_paths` 里的文件，改到别处算 `wrong_files`。

## 之前报告缺什么

旧报告能告诉你通过率、工具调用数和成本，但有些问题看不出来：

- 一个任务改了三个文件，其中两个是无关文件，但它仍然通过了 hidden tests。报告不会提示“它改错了地方”。
- 没有 trace 的 baseline（比如 `bare`）会显示 `avg_approvals=0`，看起来像“没有审批”，其实是“没有数据”。
- 只给总 token 和总成本，看不出平均每个 run 花多少。
- 验证脚本抛异常时，失败原因可能被归到别处。

## `wrong_files` 怎么判

`src/minicode/evals/classify.py` 增加了 `_changed_wrong_files()`（[`classify.py#L45`](../../src/minicode/evals/classify.py#L45)）。逻辑是：

1. 只有 `task.toml` 声明了非空 `expected_paths` 才启用。
2. 从结果里的 `changed_paths` 或 trace 的 `touched_paths` 拿到实际改过的路径。
3. 做路径归一化，逐个和 `expected_paths` 比。
4. 只要有一个路径不在期望集合里，就返回 `wrong_files`。

这条规则只在失败分类里生效：任务已经通过时不会再被改成失败。它也不是“改了别的文件就一定错”，而是“任务作者声明了期望路径，你改到了集合外”。没有声明 `expected_paths` 的任务照旧走后面的分类。

`task.toml` 里可以这样写：

```toml
expected_paths = ["src/app.py"]
```

`load_task()` 会校验它必须是字符串列表，类型不对直接报错。结果里会带上 `expected_paths` 和 `changed_paths`，方便报告解释。

## 分类顺序

`classify_failure()`（[`classify.py#L58`](../../src/minicode/evals/classify.py#L58)）现在按证据排优先级。几个容易混的点：

- 上下文溢出先于 worker 状态判断，因为溢出会表现成 worker 失败。
- `permission_denied` 先于 `agent_error`，避免把策略拒绝说成模型崩了。
- `wrong_files` 放在 `agent_error` 之后、`loop` 之前；它需要 trace/结果里的路径证据。
- verify 抛异常时优先归为 `verification_failed`，即使 agent 没有跑测试。

分类是确定性的，不调用模型。这样同一份报告重跑会得到同样的原因，不会因为“模型觉得”而变。

## 报告指标

`runner.py` 的 `summarize()`（[`runner.py#L423`](../../src/minicode/evals/runner.py#L423)）补了这些字段：

- `task_pass_counts`：每个任务通过了几次。
- `trace_runs`：有多少 run 带 trace。
- `avg_input_tokens` / `avg_output_tokens` / `avg_total_tokens`：按 run 平均。
- `avg_cost_usd`：按 run 平均成本。
- `avg_duration_s`：按 run 平均耗时。
- `avg_approvals` / `avg_blocked`：没有 trace 时返回 `null`，终端打印 `n/a`。

`null` 比 `0` 诚实。`0` 会被读成“有 trace，但一次审批都没有”；`null` 表示“这个 baseline 根本没写 trace”。

## 代价和边界

`wrong_files` 依赖 trace 里的写/编辑/删除事件。如果某个工具没有记录路径，或者任务没有声明 `expected_paths`，这条规则就不会触发。trace 只在评测里写，报告只保留摘要，不保留原始工具输出；fixture 里不要放 secret。

## 测试

`tests/test_evals.py` 覆盖 `expected_paths` 的读取和非法类型；`tests/test_evals_classify.py` 覆盖 `wrong_files` 和分类顺序；`tests/test_evals.py` 还覆盖没有 trace 时 `avg_approvals` 为 `None`、`trace_runs` 和 pass@k 汇总。`tests/test_evals_cli.py` 检查报告字段能正确打印。

## 读完后你应该能回答

1. 什么情况下才会出现 `wrong_files`？
2. 为什么没有 trace 时 `avg_approvals` 要返回 `null` 而不是 `0`？
3. `verification_failed` 和 `agent_error` 的边界在哪？
