# `ask`、`yolo`、`read-only` 什么时候用

三种模式的区别不是“松紧”，而是“谁做决定”：

- `read-only`：`Policy` 直接拒绝。
- `ask`：把决定推给人。
- `yolo`：跳过人，但跳不过 hard deny。

## 一张表

| 模式 | 文件写/删 | safe shell | 其他 shell | hard deny | 非 TTY |
| --- | --- | --- | --- | --- | --- |
| `read-only` | 拒绝 | 允许 | 拒绝（除非 allow-list 显式加入） | 拒绝 | 拒绝非 safe 命令 |
| `ask` | 审批 | 允许 | 审批 | 拒绝 | gated action 自动拒绝 |
| `yolo` | 允许 | 允许 | 允许 | 拒绝 | 不受影响 |

hard deny 在三种模式里都先判，见 [`evaluate_command()`](../../src/minicode/policy.py#L413)；`yolo` 只是跳过 HITL，不会放行 `rm -rf /`、`git push --force`。文件写入在 `read-only` 下由 [`PolicyShellBackend.write()`](../../src/minicode/backends.py#L28) 直接拒绝；shell 由 [`execute()`](../../src/minicode/backends.py#L18) 拒绝。

## `read-only` 什么时候用

适合“只看不改”：

- 审 PR、读陌生仓库、解释代码结构；
- 安全审查、确认某条命令会不会改文件；
- CI 里只做检查，不允许 agent 写工作区。

典型命令：

```bash
uv run minicode --permission-mode read-only "review this change"
uv run minicode --permission-mode read-only "explain the repository structure"
```

它允许 `ls`、`cat`、`grep`、`rg`、`git status`、`git diff`、`git log` 这类 safe 命令；`uv run pytest` 不在 safe list，默认会被拒绝。它适合“只读审查”，不适合“修完再验证”。

注意两个边界：

- `read-only` 不是保密模式：`cat ~/.ssh/id_rsa` 仍然命中 `cat` 的 safe 前缀，会被执行。它只表示“不改状态”。
- `--shell-allow-list` 加的 prefix 会进入 `_allow_commands`，在 `read-only` 下也会被当作 safe；不要用它给 `rm`、`git commit` 这类会改状态的命令开口子。

## `ask` 什么时候用

这是默认模式，适合正常的本地开发：

- 你信任这个 workspace，但想先看 agent 要改什么、跑什么；
- 你在交互终端里，能按 `y/N`；
- 你想让 `git status` 这类命令直接跑，但 `edit_file`、`uv run pytest` 先停下来。

典型命令：

```bash
uv run minicode "fix the failing test"
uv run minicode --shell-allow-list "uv run pytest" "check the tests"
```

默认 `ask` 的行为：

- `write_file`、`edit_file`、`delete` 总是先审批，见 [`file_gate`](../../src/minicode/agent.py#L166)；
- `execute` 只在 `Policy` 返回 `ASK` 时才审批，见 [`execute` 的 `when`](../../src/minicode/agent.py#L174)；
- `git status`、`ls`、`cat` 这种 safe 命令直接跑；
- `rm -rf /` 这种 hard deny 不弹审批，直接由 backend 拒绝并返回 126；
- 非 TTY 下 gated action 自动拒绝，不阻塞，见 [`ask_approval()`](../../src/minicode/cli.py#L184)。

`--shell-allow-list` 适合减少重复审批，例如把 `uv run pytest` 加进去；但它只影响 shell 分类，文件写入仍然要审批。

## `yolo` 什么时候用

适合“环境可丢弃、任务可信、没人可问”的场景：

- 容器/VM/临时目录里跑批量任务；
- eval worker 这类非交互子进程，见 [`run_full()`](../../src/minicode/evals/worker.py#L70)；
- 你完全信任仓库和模型，愿意接受它直接改文件、跑命令。

典型命令：

```bash
uv run minicode --permission-mode yolo "fix the tests"
```

`yolo` 下：

- 文件写/删直接放行；
- shell 直接执行，除非命中 hard deny；
- hard deny 仍然返回 126；
- 不会弹审批，所以非 TTY 也能用。

不要把 `yolo` 用在不可信仓库、生产环境或含敏感凭据的机器上。它没有 sandbox，只是跳过审批。

## 怎么选

- 只想读、审查、解释：`read-only`。
- 正常改代码、想保留人的决定：`ask`（默认）。
- 容器/临时目录/评测/完全信任：`yolo`。
- 无 TTY 的脚本或 CI：`ask` 会把 gated action 拒绝；要么用 `yolo`，要么用 `--shell-allow-list` 明确放行需要的命令。
- 不确定：先用 `read-only` 看它想做什么，再切 `ask` 让它做。

最后记住：三种模式都是 guardrail，不是 sandbox。`read-only` 仍能读用户有权限的文件，`yolo` 仍能执行 hard deny 之外的命令；不可信任务用容器或 VM。
