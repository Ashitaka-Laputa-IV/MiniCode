# TTY 和 gated action

## TTY

TTY 是“交互终端”的旧称。在这个项目里，判断标准就是 `sys.stdin.isatty()`：标准输入是否连着可交互的终端。

- [`ask_approval()` 里的 `interactive = sys.stdin.isatty()`](../../src/minicode/cli.py#L174)
- 非 TTY 时走 [`if not interactive`](../../src/minicode/cli.py#L184)，直接 reject，不阻塞。
- `main()` 也用同一个判断决定“没有 prompt 时要不要从 stdin 读任务”，见 [`main()`](../../src/minicode/cli.py#L401)。

例子：

- 在 Windows Terminal 里跑 `uv run minicode "..."`，`isatty()` 通常为真，审批时会显示 `approve? [y/N]`。
- `echo "fix it" | uv run minicode`、CI、子进程捕获 stdin 时，`isatty()` 为假，gated action 会被自动拒绝。

## gated action

gated action 是本项目对“被审批门挡住的 tool call”的简称。范围由 [`build_agent()` 的 `interrupt_on`](../../src/minicode/agent.py#L159) 决定：

- `write_file`、`edit_file`、`delete`：在 `ask` 下总是 gate。
- `execute`：只有 [`needs_shell_approval()`](../../src/minicode/agent.py#L162) 返回真时才 gate，也就是 [`Policy.evaluate_command()`](../../src/minicode/policy.py#L413) 返回 `ASK` 的命令。
- `git status`、`ls`、`cat` 这类 safe 命令不 gate。
- `rm -rf /` 也不是 gate，而是 hard deny；它不会弹审批，直接进工具节点，由 [`PolicyShellBackend.execute()`](../../src/minicode/backends.py#L18) 返回 126。

正确流程是：

模型发出 tool call → HITL 在 `after_model` 暂停 → CLI 收集 approve/reject → resume 从暂停点继续，应用 decision → 工具节点执行 → 结果回到模型。

不是“resume 后重新跑模型”。相关代码见 [`run_turn()`](../../src/minicode/cli.py#L224) 和 [`resume_command()`](../../src/minicode/cli.py#L211)，真实 stream 的回归用例见 [`test_run_turn_handles_real_stream_interrupt`](../../tests/test_hitl.py#L159)。
