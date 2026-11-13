# REPL 有审批吗？

有。REPL 默认也是 `ask` 模式，所以 gated action 会停下来问 `approve? [y/N]`。

那张表的问题是：它只回答“状态存在哪里”，没有回答“有没有审批”。`checkpointer` 和 `permission_mode` 是两条独立的线：

- `checkpointer` 决定对话状态活多久；
- `permission_mode` 决定 tool call 要不要审批、要不要拒绝。

REPL 只是“把 checkpointer 换成 SQLite”，并没有关掉审批。默认启动：

```bash
uv run minicode -i
```

`--permission-mode` 的默认值是 `ask`，见 [`--permission-mode` 的默认值](../../src/minicode/cli.py#L343)；`build_agent()` 在 `ask` 下会组装 [`interrupt_on`](../../src/minicode/agent.py#L159)。所以 REPL 里 `write_file`、`edit_file`、`delete` 和需要审批的 `execute` 仍然会暂停。

## 把三条线拆开看

| 场景 | 审批 | checkpointer |
| --- | --- | --- |
| 单次任务，`ask` | 有，gated action 暂停 | `InMemorySaver` |
| 单次任务，`read-only`/`yolo` | 没有 HITL：前者拒绝，后者放行 | 无 |
| REPL，`ask` | 有，gated action 暂停 | `SqliteSaver` |
| REPL，`read-only` | 没有 HITL，backend 拒绝 | `SqliteSaver` |
| REPL，`yolo` | 没有 HITL，backend 放行（hard deny 仍拒） | `SqliteSaver` |

REPL 之所以在表里只写一行，是因为它无论哪种权限模式都用 SQLite：`main()` 在 REPL 路径传 `checkpoint=True`，见 [`checkpoint=not bool(prompt)`](../../src/minicode/cli.py#L422)；[`build_agent()` 的 checkpointer 分支](../../src/minicode/agent.py#L181) 会优先用 `SqliteSaver`。

审批则看 `permission_mode`：

- `ask`：有 HITL；
- `read-only`：没有 HITL，backend 直接拒绝写入和非 safe 命令；
- `yolo`：没有 HITL，backend 直接放行，但 hard deny 仍然返回 126。

## REPL 和单次任务的区别

不是“REPL 有审批、单次没有”，而是：

- 单次 `ask` 也要审批，只是状态用 `InMemorySaver`，够 interrupt/resume 就行；
- REPL `ask` 也要审批，但状态用 `SqliteSaver`，因为下一轮进程还要接着聊。

所以 `--thread`/`--db` 只影响 REPL 的会话持久化，不影响审批开关。要关审批，改的是 `--permission-mode`，不是 checkpointer。

一句话：REPL 默认有审批；表里的 `SqliteSaver` 只说明状态活多久，不说明有没有人把关。
