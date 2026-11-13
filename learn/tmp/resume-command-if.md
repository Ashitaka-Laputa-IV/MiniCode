# `resume_command()` 里的 `if` 还有必要吗

结论：从 LangGraph 的正确性看，不是必需；从当前代码的可读性和测试契约看，建议保留。

## 为什么不是必需

`Command.resume` 支持两种形态：

- 单个值，直接恢复下一个 interrupt；
- `{interrupt_id: value}`，按 interrupt id 恢复。

当前依赖的 LangGraph 在 `Command` 的 docstring 里明确写了这两项。单 interrupt 用 id-keyed map 也能正常恢复；我用 `ToolCallingModel` 触发 `write_file` 审批，再发送 `Command(resume={interrupt.id: {"decisions": [{"type": "approve"}]}})`，resume stream 正常走到 `HumanInTheLoopMiddleware.after_model` → `tools` → `model`。

所以把 [`resume_command()`](../../src/minicode/cli.py#L211) 的 213–221 行统一成：

```python
return Command(
    resume={
        interrupt.id: {"decisions": ask_approval(interrupt, progress)}
        for interrupt in interrupts
    }
)
```

功能上是可行的。

## 为什么现在不建议直接删

第一，测试锁定了单 interrupt 的 resume 形状。[`test_run_turn_approves_interrupt`](../../tests/test_cli.py#L384) 直接断言：

```python
assert agent.inputs[1].resume == {"decisions": [{"type": "approve"}]}
```

[`test_run_turn_rejects_interrupt_without_tty`](../../tests/test_cli.py#L399) 也按 `resume["decisions"]` 读取。统一成 id-keyed map 后，这两个断言都要改成先取 interrupt id。

第二，单 interrupt 是主路径，直接传值不依赖 `interrupt.id` 是否稳定、是否唯一；多 interrupt 才需要 id 映射。

第三，这个 `if` 把 LangGraph 的两种 resume 协议显式分开了：单值对应单个 interrupt，map 对应多个 interrupt。读者不用先知道 LangGraph 接受“单元素的 id map”才能看懂。

## 如果确实要删

删掉后需要同步改两条 CLI 测试，并跑：

```bash
uv run pytest -q tests/test_cli.py tests/test_hitl.py
```

单 interrupt 的真实图测试仍然会通过；失败的是断言 resume 形状的 fake-agent 测试，不是 LangGraph 行为。
