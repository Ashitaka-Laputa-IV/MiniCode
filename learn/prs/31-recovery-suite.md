# PR #31：用两个进程验证 checkpoint 恢复

一句话：这个 PR 加了一套恢复评测。它让 agent 在第一次 HITL 审批时停住，进程退出；再用同一个 SQLite checkpoint 和 thread 启动第二个进程，批准后把任务做完。

## 为什么需要单独测

REPL 的 SQLite checkpoint 早就有了，但“有 checkpoint”不等于“中断后能恢复”。真正要验证的是：

- 第一个进程停下时，待审批动作有没有写进 checkpoint？
- 第二个进程能不能从同一个 thread 接着走，而不是从头再来？
- 没有 checkpoint 时，恢复是不是应该失败？

这些问题跨进程、跨时间，普通单元测试里用一个进程模拟不出来。恢复套件就是把这个过程拆成两个 worker 子进程。

## 两阶段怎么走

`src/minicode/evals/recovery.py` 的 `run_recovery_case()`（[`recovery.py#L248`](../../src/minicode/evals/recovery.py#L248)）准备一个临时 SQLite 数据库和一个固定的 thread id，然后：

**Phase 1** 用 `pause_on_interrupt=True` 启动 worker。agent 在第一个 HITL 审批请求处停住，worker 返回 `interrupted`、`interrupt_id`、`pending_actions`、`thread_id`、`checkpoint_db`，以及部分的 trace、usage 和工具计数。它不会自动恢复，也不会写 `result.txt`。

**Phase 2** 用同一个数据库和 thread 启动第二个 worker，开头就发：

```python
Command(resume={"decisions": [{"type": "approve"}]})
```

这次审批通过，agent 继续执行，最后必须把 `RECOVERY_OK` 写进 `result.txt`。评测检查这个文件内容，而不是让模型自己说“我完成了”。

fixture 是 [`evals/tasks/recovery-write/`](../../evals/tasks/recovery-write/)，提示很直接：写 `result.txt`。这样“恢复成功”有一个可执行、可读的判据。

## 对照组：没有 checkpoint

套件还会跑一个 `disable_checkpoint=True` 的对照，阶段和上面一样。对照的预期是恢复失败：

- Phase 1 仍然能在第一个 interrupt 停住，因为 worker 进程内有 `InMemorySaver` 让 HITL 能暂停。
- 但它不会创建 SQLite 数据库，`thread_id` / `checkpoint_db` 在 worker 结果里是 null。
- Phase 2 没有可恢复的状态，所以不应该完成同一个 thread。

`no_checkpoint_control_failed` 为 true 表示对照“按预期失败”了，不是 bug。还有一点：如果第二个进程完全从头执行并写了 `result.txt`，报告会标成 `fresh_execution`，不算恢复。恢复的定义是“接着同一个 thread 走”，不是“最后文件对了”。

## 怎么检查 checkpoint

`inspect_checkpoint()`（[`recovery.py#L93`](../../src/minicode/evals/recovery.py#L93)）用 `SqliteSaver.get_tuple()` 确认 thread 存在，再用 `SqliteSaver.list()` 把历史 checkpoint 的 `channel_values` 和 `pending_writes` 合并起来。

为什么要合并？LangGraph 的 checkpoint 存的是 channel 增量，不是每次一份完整状态。只看最新 tuple 可能漏掉更早的 `ToolMessage`。合并后才能数出消息数、`tool_messages` 和重复的工具调用（重复 id 或相同签名）。

报告里每个任务有 `recovery_success`、`phase1_interrupted`、`phase2_completed`、`checkpoint_exists`、`tool_messages`、`repeated_tool_calls`、`final_completion`、`no_checkpoint_control_failed`、耗时、usage 和成本；汇总里有恢复率、对照通过率、总工具消息数、成本和墙钟时间。

## 怎么跑

```bash
uv run minicode eval --suite recovery --baseline minicode-ask --json evals/results/recovery-ask.json
```

只允许 `minicode-ask`（[`evals/cli.py#L92`](../../src/minicode/evals/cli.py#L92)）。恢复路径依赖 HITL 先停下来，用 `yolo` 就没有中断可恢复。这个套件也不在 PR CI 里跑。

## 边界

当前 fixture 只有一个 gated write，所以 `--resume-approve` 只发一个批准决策。如果以后的提示同时产生多个 interrupt，就需要为每个 interrupt 准备决策，不能只发一个。

它验证的是 checkpoint 持久化和 resume 流程，不验证所有中断类型。`disable_checkpoint` 对照能说明“没有持久化就恢复不了”，但它不是安全测试，也不证明 SQLite 文件不会被篡改。

## 读完后你应该能回答

1. Phase 1 为什么必须退出，而不是在同一个进程里等审批？
2. 为什么“第二个进程从头跑并写对了文件”不算恢复？
3. 为什么检查 checkpoint 要合并 `channel_values` 和 `pending_writes`？
4. 多 interrupt 的场景需要改哪里？
