# 复习计划与练习

这篇是给「想补课但不想从第一行读到最后一行」用的。可以按时间选一条路径。

## 路径 A：只有 30 分钟

1. 读 [简介](01-introduction.md) 的「当前能力」和「不是什么」。
2. 读 [心智模型](02-mental-model.md) 的「两条运行路径」「HITL 审批状态机」「策略判定流程」。
3. 读 [代码导读](04-code-tour.md) 的「推荐阅读顺序」和「`cli.py` 详解」。
4. 记住三句话：
   - `cli.py` 管怎么运行，`agent.py` 管运行什么，`policy.py` 管什么能做。
   - 单次 `ask` 也有 InMemorySaver；REPL 才有 SQLite。
   - hard deny 在 yolo 下仍生效；approve 不等于绕过它。

## 路径 B：3 天补课

### Day 1：CLI 和 agent 主路径

目标：能说清一条 prompt 从输入到最终回答经过了哪些函数。

- 读：01、02、04 的入口/单次任务/REPL 部分。
- 跑：

```bash
uv run pytest -q
uv run minicode --help
```

- 练习：
  1. 在 `cli.main()` 里标出 `build_agent`、`run_turn`、`interactive_loop` 的调用位置。
  2. 解释为什么单次任务 `checkpoint=False`，但 ask 模式仍然有 checkpointer。
  3. 解释 `--db` / `--thread` 为什么不能和 prompt 一起用。

### Day 2：策略、审批和状态

目标：能解释 read-only / ask / yolo 的差异，以及一次审批怎么 resume。

- 读：02 的 HITL/策略部分；04 的 `policy.py`、`backends.py`、`cli.py` 审批部分。
- 跑：

```bash
uv run pytest -q tests/test_policy.py
uv run pytest -q tests/test_hitl.py
uv run pytest -q tests/test_sqlite.py
```

- 练习：
  1. 用 `Policy` 分别判定 `git status`、`curl https://example.com`、`rm -rf /`、`python script.py`。
  2. 解释为什么 `PolicyShellBackend` 还要再查一次 hard deny。
  3. 解释 `reset_thread()` 为什么删除当前 thread，而不是生成新 id。
  4. 解释非 TTY 下为什么必须 reject，而不是等待。

### Day 3：评测、CI 和 PR 历史

目标：能说清「怎么证明 agent 真的能改代码」，以及最近 PR 各自解决什么问题。

- 读：02 的评测部分；04 的 `evals/` 和测试导读；05 的 PR #7、#9、#10、#13、#15。
- 跑（不花钱的部分）：

```bash
uv run pytest -q tests/test_evals.py tests/test_evals_cli.py tests/test_evals_worker.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

- 可选（会调用模型、有成本）：

```bash
uv run minicode eval --task fix-import --baseline full
```

- 练习：
  1. 解释 `full` 和 `bare` 的区别。
  2. 解释为什么验证环境不能带 provider key。
  3. 解释 hidden tests 为什么放在 workspace 外。
  4. 用 05 的「审阅主题回顾」检查一个 PR。

## 路径 C：1 周深读

| 天 | 主题 | 产出 |
| --- | --- | --- |
| 1 | CLI / agent / env | 画出一次单次任务的调用链 |
| 2 | policy / hard deny | 列出 10 条 dangerous 命令并写测试 |
| 3 | HITL / checkpointer | 画出 interrupt → approve → resume 状态图 |
| 4 | SQLite / thread | 用两个 thread 验证隔离，观察 db 文件 |
| 5 | evals / hidden tests | 新增一个最小 eval 任务并跑 `--task` |
| 6 | CI / live 流程 | 本地跑一遍 CI 命令，读懂 live workflow |
| 7 | PR 历史 / 复盘 | 给 #15 写一段 200 字审阅总结 |

## 动手练习

### 练习 1：策略判定

在仓库根目录运行一个 Python 片段：

```python
from minicode.policy import PermissionMode, Policy

commands = [
    "git status",
    "curl https://example.com",
    "rm -rf /",
    "python script.py",
    "git push --force",
]

for mode in PermissionMode:
    policy = Policy(mode)
    print(mode.value)
    for command in commands:
        decision = policy.evaluate_command(command)
        print(f"  {command!r}: {decision.action.value} ({decision.reason})")
```

期望：

- `git status`：所有模式 ALLOW。
- `curl ...`：read-only DENY，ask ASK，yolo ALLOW。
- `rm -rf /`：所有模式 DENY。
- `python script.py`：read-only DENY，ask ASK，yolo ALLOW。
- `git push --force`：所有模式 DENY。

### 练习 2：引号与 wrapper

```python
from minicode.policy import PermissionMode, Policy

policy = Policy(PermissionMode.YOLO)
for command in [
    "grep '| sh' notes.md",
    "bash -c 'rm -rf / && echo ok'",
    "sudo rm -rf /",
    "env VAR=1 rm -rf /",
]:
    print(command, "->", policy.evaluate_command(command).action.value)
```

问题：

- 为什么 `grep '| sh'` 不应该被 hard deny？
- 为什么 `bash -c 'rm -rf / && echo ok'` 必须被 hard deny？
- `sudo` / `env` 包装为什么要在判定前剥离？

### 练习 3：一次审批

用 fake model 写一个小测试，或者直接读 `tests/test_hitl.py`：

- `write_file` 在 ask 下触发 interrupt；
- approve 后文件落盘；
- reject 后文件不存在；
- read-only 不触发 interrupt，直接拒绝；
- yolo 不触发 interrupt，直接写入。

尝试回答：为什么 approve 之后仍要经过 `PolicyShellBackend`？

### 练习 4：SQLite 会话

```bash
uv run minicode -i --thread demo --db .minicode/demo.sqlite
```

在 REPL 里输入一句话（会调用模型），然后 `/exit`。再次启动同一个 `--thread` / `--db`，看它是否记得上下文。然后 `/reset`，确认当前 thread 被清空。

观察：

- `.minicode/demo.sqlite` 是否存在；
- `--thread` 不同但 `--db` 相同时，会话是否隔离；
- 并行 REPL 为什么可能 `database is locked`。

### 练习 5：新增一个 safe 命令

假设要允许 `git branch`（只读）：

1. 在 `SAFE_COMMAND_PREFIXES` 加 `git branch`。
2. 在 `tests/test_policy.py` 加：
   - `git branch` 在 read-only / ask 下 ALLOW；
   - `git branch -D foo` 是否应该 ALLOW？如果不应该，怎么拦？
3. 想想：`git branch` 既能列分支，也能删分支；只加前缀安全吗？

这个练习的目的是体会「safe 列表不能只看命令名」。

### 练习 6：新增 hard deny 规则

假设要拦 `shutdown -h now`：

1. 在 `_segment_hard_denied()` 里找 `shutdown` 分支。
2. 加测试：
   - `shutdown -h now` 在所有模式 DENY；
   - `grep shutdown notes.md` 不被误伤。
3. 再想想 Windows 的 `shutdown /s /t 0` 是否也能覆盖。

### 练习 7：新增 eval 任务

1. 复制一个最小 task，例如 `evals/tasks/fix-import/`。
2. 改 fixture，让它有一个小 bug。
3. 写 `prompt.md`，要求明确、可验证。
4. 加 hidden test 或 `verify.py`。
5. 加入 `evals/suites/smoke.toml`。
6. 先跑：

```bash
uv run minicode eval --task <id> --baseline full
```

7. 再跑 smoke（有成本，确认需要时再跑）。

### 练习 8：审阅一个 PR

用 05 的「审阅主题回顾」检查 #15：

- 策略是否可绕过？
- 非 TTY 是否 fail closed？
- approve 后是否仍走 hard deny？
- 测试是否覆盖真实 interrupt/resume？
- 文档是否还写着「没有 HITL」？

## 自测题

先自己回答，再展开看参考答案。

<details>
<summary>1. 为什么单次 ask 任务需要 InMemorySaver？</summary>

LangGraph 的 interrupt/resume 需要 checkpointer。单次任务不写 SQLite，但审批仍要暂停和恢复，所以用进程内 `InMemorySaver`。

</details>

<details>
<summary>2. 为什么 read-only 不是沙箱？</summary>

它只限制文件工具和 shell 命令的分类；shell 仍以当前用户权限运行，能访问用户能访问的路径。没有 OS 级隔离、资源限制或网络隔离。

</details>

<details>
<summary>3. `PolicyShellBackend` 和 `interrupt_on` 分别负责什么？</summary>

`interrupt_on` 负责 ask 模式的暂停/审批；`PolicyShellBackend` 负责执行前的 hard deny 和 read-only 文件拒绝。前者是交互层，后者是最后兜底。

</details>

<details>
<summary>4. 为什么 approve 之后还要再查 hard deny？</summary>

用户可能批准了危险命令，但 hard deny 是「连 yolo 都不能执行」的最低线。审批不能覆盖它。

</details>

<details>
<summary>5. 为什么 `bare` baseline 失败时退出码是 0？</summary>

`bare` 是能力下限，失败是预期信息；它用来对比「纯模型」和「带工具」的差距，不应该让 CI 失败。

</details>

<details>
<summary>6. 为什么 hidden tests 放在 workspace 外？</summary>

避免 agent 在运行过程中看到或修改验证代码；这是 convention-level 隔离，不是沙箱。

</details>

<details>
<summary>7. 为什么验证环境要过滤 provider key？</summary>

验证只需要跑 pytest/脚本，不需要调用模型；过滤 key 降低泄露风险。

</details>

<details>
<summary>8. 为什么 `.env` 不加载 base URL / endpoint？</summary>

陌生仓库的 `.env` 不应能把 API key 重定向到其他地址。Azure endpoint 等变量应在 shell 设置。

</details>

<details>
<summary>9. 为什么 `reset_thread()` 删除当前 thread，而不是换新 id？</summary>

删除 checkpoint 就能清空上下文；保留 id 让 CLI 参数和日志稳定。关键是避免恢复未完成节点。

</details>

<details>
<summary>10. 为什么非 TTY 审批要 reject？</summary>

不能阻塞 CI/管道等待输入；fail closed 比挂起安全。

</details>

<details>
<summary>11. 为什么 `--shell-allow-list all` 在 read-only 下无效？</summary>

read-only 的语义是只允许 safe 命令；`all` 会让它变成「所有命令都只读」，破坏模式保证。

</details>

<details>
<summary>12. 为什么 `git branch` 不能简单加进 safe 列表？</summary>

`git branch` 可以列分支，也可以 `-D` 删除分支；只匹配命令名不够，还要限制参数。

</details>

<details>
<summary>13. 为什么 `print_update()` 既打印又返回 message？</summary>

它消费 stream chunk 时顺便记录最后一个 AI message，避免再遍历一次。当前规模可接受；如果逻辑变复杂，可以拆成 render 和 extract。

</details>

<details>
<summary>14. 为什么 `checkpoint=True` 只给 REPL？</summary>

单次任务不需要跨进程会话；强制 SQLite 会让调用方必须管理 db/thread。REPL 才需要持久化。

</details>

<details>
<summary>15. 为什么 CI 不跑 live 测试和 smoke？</summary>

它们调用真实模型，有成本、耗时、可能抖动；PR CI 只跑便宜稳定的单元测试和静态检查。

</details>

## PR 审阅清单

以后看新 PR，可以按这个顺序：

1. **行为**：这个改动在什么模式下生效？read-only / ask / yolo 分别怎样？
2. **失败路径**：非 TTY、缺 key、网络失败、SQLite 锁、验证超时，会怎样？
3. **状态**：checkpointer、连接、临时目录、thread 是否正确关闭/清理？
4. **安全**：策略能否被引号、wrapper、重定向、危险参数绕过？
5. **测试**：是否覆盖真实路径，而不只是 fake happy path？
6. **评测**：hidden tests 是否在 workspace 外？验证环境是否没有 key？
7. **成本**：是否把 live/smoke 加进 PR CI？
8. **文档**：是否还在说「没有 HITL」「MemorySaver」「deepseek-chat」等过时信息？

## 术语表

| 术语 | 含义 |
| --- | --- |
| HITL | Human-in-the-loop，人在回路审批 |
| interrupt | LangGraph 在工具执行前暂停图 |
| resume | 用 `Command(resume=...)` 继续被中断的图 |
| checkpointer | 保存图状态的组件；SQLite 或 InMemory |
| thread | 一个会话 id，对应一组 checkpoint |
| safe | 无元字符、参数安全、在 allow-list 中的简单命令 |
| hard deny | 所有模式都拒绝的灾难命令 |
| guardrail | 提高下限的策略层，不是沙箱 |
| sandbox | OS/容器级隔离；当前没有 |
| baseline | 评测对照组；`full` 有工具，`bare` 无工具 |
| pass@1 | 每个任务只尝试一次时的通过率 |
| fixture | 评测用的最小仓库 |
| hidden tests | agent 运行时不放进 workspace 的验证测试 |
| live | 真实调用模型、需要 API key 的测试/评测 |

## 如果文档过时了

1. 先看 `dev` 的 `README.md`、`AGENTS.md` 和测试。
2. 跑一遍：

```bash
uv run pytest -q --cov=minicode --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

3. 更新 `learn/README.md` 的「当前快照」。
4. 更新 05 的 PR 表：新合并的 PR、尚未合并的 PR。
5. 如果权限/审计/评测行为变了，同步更新 02 和 04。
6. 最后跑 `uv run ruff format learn`，避免代码块格式问题。

## 一句话

先跑起来，再沿着 `main()` 读一条路径；把「策略、审批、checkpointer、评测」四件事分开理解，代码就不难了。
