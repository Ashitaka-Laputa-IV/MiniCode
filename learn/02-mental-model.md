# 一次请求的生命周期

判断：一次 `uv run minicode "fix the failing test"` 只在三个地方交接控制权：CLI 决定会话怎么开始、怎么显示，agent 图决定模型下一步做什么，policy/backend 决定某个 tool call 能不能落地。其余都是状态在搬运。

先记住主线：`main()` 解析出 prompt → `build_agent()` 装配图和权限 → `run_turn()` 消费模型/工具循环 → `PolicyShellBackend` 执行或拒绝 → 最终回答进 stdout。下面按这条线走，不按目录走。

## 入口先把三种运行方式分开

`minicode` 的 console script 指向 `minicode:main`，所以所有路径都从 [`main()`](../src/minicode/cli.py#L382) 开始。它先看 `argv[0]` 是不是 `eval`，是就转给评测 CLI；普通任务才进入 `argparse`。这个顺序意味着 `minicode eval --help` 和 `minicode --help` 是两套参数，改主 parser 时不要假设 `eval` 也在里面。

普通路径先组装 prompt：命令行参数用空格拼起来；`--interactive` 和 prompt 同时出现直接报错；没有 prompt、没有 `-i`、stdin 又不是 TTY 时，读 stdin 当 prompt。读完之后才检查 `--db`/`--thread`，所以 `echo task | minicode --db state.sqlite` 也会得到“SQLite 参数只属于交互模式”的错误，而不是静默忽略。这些分支都在 [`main()` 的 prompt 解析段](../src/minicode/cli.py#L398)。

`load_env()` 在 parse 之后运行，只把 `MINICODE_MODEL` 和已知 provider key 写进 os.environ；`OPENAI_BASE_URL` 这类端点变量会被忽略。shell 里已有的值优先，因为写入用的是 `setdefault`。`--debug` 会把实际加载的 `.env` 路径打到 stderr，方便排查“为什么读到的不是这个 key”，见 [`load_env()`](../src/minicode/cli.py#L40)。

然后 `main()` 决定这次是单次任务还是 REPL。单次任务传 `checkpoint=False`，REPL 传 `checkpoint=True`；两种都创建 `config = {"configurable": {"thread_id": ...}}`，但只有 REPL 的 `--thread`/`--db` 有意义。`thread_id` 默认是 `default`，见 [`main()` 的 checkpoint 选择](../src/minicode/cli.py#L422)。

单次任务和 REPL 的失败处理也不同。单次任务里 `KeyboardInterrupt` 返回 130，普通异常打印错误并返回 1；REPL 里失败或 Ctrl+C 会清掉当前 thread 再继续下一条输入。`--debug` 时普通异常两边都重新抛出，保留 traceback，见 [`interactive_loop()` 的异常分支](../src/minicode/cli.py#L299)。

## `build_agent()` 把三层接在一起

[`build_agent()`](../src/minicode/agent.py#L132) 不做对话，它只做装配：解析 workspace 和模型名、解析权限模式、创建 `Policy`、创建 `PolicyShellBackend`、决定 `interrupt_on`、决定 checkpointer，再交给 `create_deep_agent()`。

第一步是根目录和模型。`resolve_root()` 会把路径 `expanduser().resolve()` 并检查 `is_dir()`；`resolve_model()` 的优先级是显式参数、`MINICODE_MODEL`、默认 `deepseek:deepseek-flash`。这两条都在 [`build_agent()` 的前几行](../src/minicode/agent.py#L147) 固定下来，所以 CLI 和库调用者拿到的是同一套校验。

第二步是权限。`PermissionMode.parse()` 把字符串转成枚举；`Policy(mode, allow_commands=...)` 持有模式和安全命令列表。`PolicyShellBackend` 拿到 `shell_env()` 过滤后的环境，并显式设置 `inherit_env=False`，所以 provider key 不会跟着 shell 命令进入子进程。这个接线在 [`build_agent()` 创建 backend](../src/minicode/agent.py#L152)。

第三步是中断配置。只有 `ask` 模式才创建 `interrupt_on`：`write_file`/`edit_file`/`delete` 无条件审批，`execute` 的审批条件由 [`needs_shell_approval()`](../src/minicode/agent.py#L162) 动态判断。`read-only` 和 `yolo` 的 `interrupt_on` 是 `None`，前者靠 backend 拒绝，后者直接放行。

第四步是 checkpointer。`checkpoint=True` 用 `SqliteSaver`，否则 `ask` 用 `InMemorySaver`，`read-only`/`yolo` 用 `None`。这一段在 [`build_agent()` 的 checkpointer 分支](../src/minicode/agent.py#L181)，它解释了为什么单次任务也可以有状态，而 REPL 的状态能活过进程。

`PolicyShellBackend` 包着 `LocalShellBackend`。文件工具的 `/` 是 workspace 根，system prompt 明确要求不要给文件工具传 Windows 盘符路径；shell 命令则把 workspace 当当前目录。这个差异写在 [`SYSTEM_PROMPT`](../src/minicode/agent.py#L64) 和 [`PolicyShellBackend` 的构造](../src/minicode/backends.py#L14)。

system prompt 不是权限策略。它告诉模型 shell 怎么用、文件路径怎么写、做完要总结；真正的放行/拒绝在 `Policy` 和 backend 里。读 prompt 时不要从里面推断“这条命令会不会被拦”，要去看 [`evaluate_command()`](../src/minicode/policy.py#L413)。

## 图里的一个回合

一次用户输入进入图后，先走模型节点。模型返回的 AI 消息可能带 `tool_calls`；有 tool call 就进工具节点，没有就是最终回答。工具节点把结果作为 tool 消息写回状态，再回到模型。这个循环直到模型不再调用工具。

`run_turn()` 用 `agent.stream(..., stream_mode="updates")` 消费这个循环，见 [`run_turn()` 的 stream 调用](../src/minicode/cli.py#L237)。每个 update 以节点名为 key；[`print_update()`](../src/minicode/cli.py#L109) 只处理带 `messages` 的节点，打印工具名和参数、工具结果、以及可选的 thinking。

最终回答不是“最后一个 update”，而是 [`print_update()` 返回的最后一条无 tool call 的 AI 消息](../src/minicode/cli.py#L144)。`run_turn()` 把它返回给 `main()`，再由 [`print_final()`](../src/minicode/cli.py#L149) 写到 stdout。工具进度和 thinking 走 stderr，最终答案走 stdout；管道里看到的只有最终答案。

`print_final()` 只在 `output.is_terminal` 为真时用 Rich `Markdown`，否则按原文打印。这个分支决定了 `minicode ... > notes.md` 拿到的是模型原文，而不是渲染后的 Markdown；改动输出层时先看 [`print_final()` 的 TTY 判断](../src/minicode/cli.py#L152)。

把主线压缩成八步，控制权的位置就清楚了：

1. `main()` 解析 prompt，决定单次还是 REPL，生成 `thread_id`。
2. `build_agent()` 解析 root/model，创建 `Policy` 和 `PolicyShellBackend`。
3. `build_agent()` 按模式和 `checkpoint` 选择 checkpointer，调用 `create_deep_agent()` 建图。
4. `run_turn()` 把用户消息作为 `{"messages": [...]}` 送进 `agent.stream()`。
5. 模型节点返回一条 AI 消息；有 `tool_calls` 就进第 6 步，没有就进第 8 步。
6. `ask` 下被 gate 的 tool call 在这里暂停；`run_turn()` 把决定收集成 `Command(resume=...)`，回到第 5 步。
7. 工具节点调用 `PolicyShellBackend`；shell 走 `execute()`，文件工具走 `write()`/`edit()`/`delete()`，结果写回消息列表，回到第 5 步。
8. 最终那条无 tool call 的 AI 消息由 `print_final()` 写到 stdout，进程结束或回到 REPL 等待下一条输入。

## ask 模式的 interrupt 在哪里发生

`ask` 模式下，[`build_agent()` 组装 `interrupt_on`](../src/minicode/agent.py#L159)：`write_file`、`edit_file`、`delete` 无条件挂文件审批，`execute` 只在 [`needs_shell_approval()`](../src/minicode/agent.py#L162) 认为命令需要审批时挂。Deep Agents 会把这份配置交给 HITL 中间件，在模型产生 tool call 之后、工具执行之前暂停。

暂停不是异常，也不是退出。`run_turn()` 在 stream 里看到 `__interrupt__` 就把 pending 收集起来，继续把这一轮 stream 消费完；stream 结束后调用 [`resume_command()`](../src/minicode/cli.py#L211) 构造 `Command(resume=...)`，再用同一个 `config` 开下一轮 stream。控制权回到图里，工具节点这时才可能执行。

人类看到的决定由 [`ask_approval()`](../src/minicode/cli.py#L169) 收集。它逐个 action 打印名称、description 和参数；stdin 不是 TTY 时直接 reject，并把原因写进 rejection message，见 [`ask_approval()` 的非 TTY 分支](../src/minicode/cli.py#L184)。一个 interrupt 里有多个 action 时，decision 的顺序必须和 `action_requests` 一致；多个 interrupt 时，`resume_command()` 用 interrupt id 分开返回。

一个具体例子：模型调用 `execute` 执行 `rm -rf build`。`Policy` 把它归为 mutating/ask；`needs_shell_approval()` 返回 true；图在工具执行前暂停。用户批准后，`run_turn()` 发回 `{"decisions": [{"type": "approve"}]}`；工具节点执行，backend 再判一次，然后 shell 返回结果。用户拒绝时，工具节点不执行，模型收到“User rejected this action. Do not retry it.”，然后继续生成回答。

批准不等于绕过 policy。`needs_shell_approval()` 只在 `evaluate_command()` 返回 `ASK` 时才停，所以 hard deny 命令根本不会弹审批，而是直接进工具节点；[`PolicyShellBackend.execute()`](../src/minicode/backends.py#L18) 再判一次，返回 exit code 126。即使有别的路径送来 approve，backend 也会再拒一次。拒绝则根本不会进 backend，模型收到 rejection message 后继续推理。

文件工具也分两段。`ask` 下 `write_file`/`edit_file`/`delete` 先被 HITL 暂停，批准后才进 backend；`read-only` 下没有 interrupt，backend 的 [`write()`](../src/minicode/backends.py#L28)、[`edit()`](../src/minicode/backends.py#L35)、[`delete()`](../src/minicode/backends.py#L48) 直接返回 permission error；`yolo` 下没有 interrupt，backend 直接放行。

## 状态存在哪里

对话状态在 checkpointer 里，按 `thread_id` 索引；每次 `agent.stream()` 都带同一个 `config`。工具产生的文件和 shell 副作用不在 checkpointer 里，它们直接落在 workspace 或 host 上。

| 场景 | checkpointer | 状态活多久 |
| --- | --- | --- |
| 单次任务，`ask` | `InMemorySaver` | 进程内，只够 interrupt/resume |
| 单次任务，`read-only`/`yolo` | 无 | 不保存 |
| REPL | `SqliteSaver` | 跨进程，`--thread`/`--db` 选择 |

单次任务也要 checkpointer，是因为 `ask` 的暂停/恢复需要图状态；没有它，`Command(resume=...)` 没有地方恢复。区别只是这个状态不需要活过进程。[`build_agent()` 的 checkpointer 分支](../src/minicode/agent.py#L181) 就是这条规则。

REPL 的 `/reset`、失败、Ctrl+C 都调用 [`reset_thread()`](../src/minicode/cli.py#L260)，它删除当前 thread 的 checkpoint，不删除 workspace 里的文件。这个区别是后面所有“重置”讨论的前提。

SQLite 默认落在 `<workspace>/.minicode/checkpoints.sqlite`，`--db` 可以换文件，`--thread` 可以换会话。连接在 `main()` 的 `finally` 里由 [`close_checkpointer()`](../src/minicode/agent.py#L124) 关闭；库调用者如果传 `checkpoint=True`，要自己负责关闭。

checkpoint 里存的是 LangGraph 的完整状态：消息列表、待执行的 tool call、pending interrupt、以及中间件的状态。它不存 workspace 的 diff，也不存 shell 的环境。工具输出会作为 tool 消息进历史，所以长会话的 SQLite 会越来越大；`/reset` 是最直接的常规清理入口。

同一个 workspace 上并行跑两个 REPL，默认都会用 `default` thread 和同一个数据库文件。`SqliteSaver` 面向单进程轻量场景，并发时可能出现 `database is locked` 或 checkpoint 交错；要并行就显式给每个实例不同的 `--thread` 和 `--db`。

## 失败路径

非 TTY 的 `ask` 不会挂住。`ask_approval()` 发现 `sys.stdin.isatty()` 为 false 时直接 reject，模型收到 rejection message，然后继续生成回答；所以 `echo "fix it" | minicode` 的退出码取决于模型是否完成，而不是取决于有没有人按键。需要自动执行时显式用 `--permission-mode yolo` 或 allow-list。

单次任务里，`KeyboardInterrupt` 被 `main()` 捕获后返回 130，普通异常打印 `minicode: ...` 并返回 1。`--debug` 会让普通异常跳过这层捕获，直接抛 traceback；这时 `finally` 仍会执行，但不要期待额外的恢复逻辑。

REPL 里，`KeyboardInterrupt` 和普通异常都会先 `reset_thread()`，再继续下一条输入。这意味着失败的那一轮不会在下一次输入时被恢复；代价是那一轮的上下文也丢了。普通异常在 `--debug` 下会让 REPL 退出，因为 debug 的用途是暴露 traceback；Ctrl+C 仍走 reset 分支。

`build_agent()` 在 `create_deep_agent()` 失败时会关闭已经打开的 checkpointer 连接，见 [`build_agent()` 的异常分支](../src/minicode/agent.py#L196)。这条路径只影响库调用者和 REPL 启动失败；单次任务没有 SQLite 连接，通常看不出来。

## 常见误判

`read-only` 不是“只能读 workspace 内的文件”。它禁止写文件、删除文件和不在 safe list 里的 shell 命令，但 `cat ~/.ssh/id_rsa` 仍然会命中 `cat` 的 safe 前缀并被执行。这个模式的语义是“不改状态”，不是“保密”。

`yolo` 不是“没有策略”。它跳过 HITL，但 `evaluate_command()` 仍然先跑 hard deny；`rm -rf /`、`git push --force` 这类命令在 yolo 下仍然返回 126。真正的风险在 hard deny 覆盖不到的命令。

`/reset` 不是撤销。它删的是对话 checkpoint；上一轮已经写出的文件、已经跑过的迁移、已经安装的依赖都还在 workspace 里。把 agent 的“记忆”与工作区的“事实”分开，是读这个项目的关键。

`--shell-allow-list` 不是“把命令加进 safe list 就完事”。`Policy.__init__` 把额外的 prefix 加到 `_allow_commands`，但 `_is_safe()` 仍然拒绝重定向、shell 元字符和危险参数；`all` 也只是在非 `read-only` 下绕过分类，hard deny 仍然先判。

所以给 `uv run pytest` 加 allow-list 时，`uv run pytest && rm -rf build` 不会整体变 safe；它按 segment 判断，第二段仍然要审批或拒绝。写 allow-list 测试时，应该同时覆盖“前缀匹配”和“复合命令”两条路径。

## 拿测试当路标

`tests/test_hitl.py` 是 interrupt/resume 的端到端样本：`write_file` 批准后落盘、reject 后不落盘、`read-only` 不触发 interrupt、`yolo` 直接写入、真实 stream 的 `run_turn` 能继续。读这一组比读中间件文档更快。

`tests/test_cli.py` 锁定非 TTY 的 reject、`/reset`、失败后清 thread、`--db`/`--thread` 与 prompt 的冲突；`tests/test_sqlite.py` 锁定跨 agent 实例的持久化。三条路径合起来，就是 02 这篇的主线。

## 三条不能忘的不变量

1. 所有 shell 执行都经过 `PolicyShellBackend.execute()`，hard deny 在 `yolo` 之前判断，见 [`evaluate_command()` 的检查顺序](../src/minicode/policy.py#L413)。新增一个能执行命令的工具，如果绕过 backend，就绕过了所有模式。
2. `ask` 的门在工具执行之前；没有批准就不会执行。批准之后 backend 还会再判一次，reject 则把决定写回模型。审批不是“只问一次”的 UI，它是图状态的一部分。
3. 对话状态和 workspace 状态是两套东西。`/reset` 或 `delete_thread()` 只清对话；文件改动、命令产生的副作用、shell 写出的文件都不会回滚。

判断规则：遇到任何新路径，先回答“这条 tool call 会不会被 gate、状态进哪个 checkpointer、输出走 stdout 还是 stderr”。三问答不上来，说明你还没定位到控制权在哪一层。
