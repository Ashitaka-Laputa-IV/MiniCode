# 按调用栈找改动点

判断：改 MiniCode 不要从目录开始，从一次 tool call 的控制权开始。下面 12 个停靠点按调用顺序排，越靠前越接近入口，越靠后越接近副作用；每站只回答三个问题：为什么停、读什么、改了会怎样。

第一次读可以分两遍。第一遍走 1–6，跟着一次请求从 CLI 进图、遇到 interrupt 再 resume；第二遍走 7–12，看 policy/backend 怎么落地、输出和评测怎么收尾。两遍之间不要打开别的文件，否则很容易把“装配”和“执行”混在一起。

行号会随着提交漂移，符号名不会。每站的链接都指向当前 HEAD 的那一行；如果你在别的分支上读，先用符号名搜索，再用行号确认。

## 1. `main()`：所有路径的入口

停在 [`main()`](../src/minicode/cli.py#L382)，因为单次任务、REPL、评测三个入口都在这里分叉。`eval` 在 `argparse` 之前被拦截，见 [`main()` 的 eval 分支](../src/minicode/cli.py#L385)；普通任务才走 `build_parser()`。

读这一段时重点看 `load_env()` 的位置、两个 `Console` 的流向、以及 `finally` 里的 [`close_checkpointer()`](../src/minicode/agent.py#L124)。改这里会影响 `--help`、退出码和资源关闭，不只是参数列表。

如果新增子命令，先决定它是像 `eval` 一样在 `main()` 前拦截，还是注册成真正的 subparser；两种做法对 `--help` 和测试的影响不同。

## 2. prompt 解析：单次还是 REPL

停在 [`main()` 的 prompt 解析段](../src/minicode/cli.py#L398)，因为这里决定“这次有没有 prompt、要不要读 stdin、能不能用 SQLite 参数”。`--interactive` 与 prompt 冲突、非 TTY 读 stdin、`--db`/`--thread` 只属于 REPL，三条规则都在这里。

读完后看 [`main()` 的 checkpoint 选择](../src/minicode/cli.py#L422)：`checkpoint=not bool(prompt)` 是单次任务和 REPL 的分界线。改这条表达式会同时改变持久化、`--db` 的语义和测试里的 `fake_build_agent` 断言。

验证时优先跑 `tests/test_cli.py` 里的 `test_main_rejects_prompt_with_interactive`、`test_main_rejects_sqlite_options_with_prompt` 和 `test_main_requires_prompt_when_not_tty`，它们分别锁 prompt/交互冲突、SQLite 参数和“非 TTY 无 prompt”。

## 3. `build_agent()`：装配点

停在 [`build_agent()`](../src/minicode/agent.py#L132)，因为 policy、backend、interrupt、checkpointer 都在这一处接线。它不产生对话，只把“用哪个模型、在哪个目录、按什么权限、状态存哪里”变成一张图。

读 147–194 行：`resolve_root()` 和 `resolve_model()` 做校验，`PermissionMode.parse()` 做模式解析，`Policy` 和 `PolicyShellBackend` 被创建，`interrupt_on` 只在 `ask` 下组装，checkpointer 再按 `checkpoint`/模式选择。

改这里最危险的是跳过校验。`resolve_root()` 的 `is_dir()` 和 `resolve_model()` 的空值回退是公开入口的契约，测试 `test_build_agent_rejects_missing_root`、`test_resolve_model_empty_falls_back` 会抓回归。

## 4. `interrupt_on`：哪些 tool call 要停

停在 [`build_agent()` 组装 `interrupt_on`](../src/minicode/agent.py#L159)，因为这是“什么需要人批准”的唯一声明。`write_file`/`edit_file`/`delete` 共用 `file_gate`，`execute` 用带 [`needs_shell_approval()`](../src/minicode/agent.py#L162) 的 `when`。

读这段时注意两点：`allowed_decisions` 只有 `approve`/`reject`，没有 `edit`；`when` 只决定“要不要停”，不决定“停之后放不放行”。放行仍由 backend 再判一次。

如果要给新工具加审批，除了在这里加 key，还要确认 CLI 的 [`ask_approval()`](../src/minicode/cli.py#L169) 能展示它的参数；如果要加 `edit` 或 `respond` 决定，`resume_command()` 和测试也要一起改。

## 5. `run_turn()`：stream 和 resume 的接缝

停在 [`run_turn()`](../src/minicode/cli.py#L224)，因为 HITL 的 bug 多数出在这个循环。它先发用户消息，再消费 `agent.stream()`；看到 `__interrupt__` 就收集，不 break；stream 结束后把 pending 变成 [`Command(resume=...)`](../src/minicode/cli.py#L211)，再开下一轮。

读 224–253 行：`stream_input` 的初始形状是 `{"messages": [{"role": "user", "content": prompt}]}`；`pending` 在每个 while 迭代开始时清空；`print_update()` 返回的 `final_message` 会被后续 update 覆盖。

改 break 条件、pending 的累积方式或 resume 的形状，最容易造成“审批后工具没执行”或“多轮 interrupt 只处理一个”。`tests/test_hitl.py` 的真实 stream 用例和 `tests/test_cli.py` 的 `ApprovalAgent` 是两条回归线。

## 6. `ask_approval()` 和 `resume_command()`：人的决定怎么变成图输入

停在 [`ask_approval()`](../src/minicode/cli.py#L169)，因为这里决定用户看到什么、decision 长什么样。它逐个 action 打印名称、description 和 `short_json(args)`；非 TTY 时 append reject；交互时读 `y/N`。

再停 [`resume_command()`](../src/minicode/cli.py#L211)：单个 interrupt 返回 `{"decisions": [...]}`，多个 interrupt 返回 `{interrupt_id: {"decisions": [...]}}`。这个形状必须和 LangGraph/LangChain 的 response schema 对齐，不能只看 CLI 测试。

改提示文案时保留参数预览。`InterruptOnConfig` 的静态 description 永远非空，所以代码仍然无条件打印 `args`，见 [`ask_approval()` 打印参数](../src/minicode/cli.py#L182)；删掉这一行会让用户“盲批”。

## 7. `Policy.evaluate_command()`：一个函数决定三种模式

停在 [`evaluate_command()`](../src/minicode/policy.py#L413)，因为所有命令分类都从这里出。顺序是：空命令 deny → hard deny → `yolo` allow → `allow_all` → safe allow → 分类 network/mutating → `read-only` deny → `ask`。

读 413–446 行时把顺序当成契约。把 `yolo` 分支移到 hard deny 之前，`rm -rf /` 就会放行；把 safe 判断移到 hard deny 之前，被 safe 前缀覆盖的 segment 就不会再进 hard deny，复合命令的风险会变大。

改分类规则时同时跑 `tests/test_policy.py` 的三组参数化用例：`read-only` 放行/拒绝、`ask` 的 ASK、hard deny 在所有模式下的 DENY。`needs_approval()` 复用同一个 `evaluate_command()`，所以它的行为会跟着变。

## 8. `_syntax_view()`、`_split_segments()`、`_is_safe()`：引号和复合命令

停在 [`_syntax_view()`](../src/minicode/policy.py#L200)，因为 safe 判断的第一步不是看命令，而是看“去掉引号字面量之后还剩什么”。单引号内容全部清空；双引号内只保留 `$` 和反引号，因为它们仍会展开。

再停 [`_split_segments()`](../src/minicode/policy.py#L158) 和 [`_is_safe()`](../src/minicode/policy.py#L457)。`_split_segments()` 按引号感知的方式切 compound command，`_segments()` 则用正则切 `_syntax_view()` 的结果；两个函数服务于不同判断，不要合并成一个。

改 `SAFE_COMMAND_PREFIXES`、`_SHELL_META_PATTERN` 或 `_SAFE_ARG_DENY` 时，至少补三类用例：引号内字面量、未加引号的 `$()`/反引号/`&`、带危险参数的 safe 命令。`tests/test_policy.py` 的 `test_quoted_literals_do_not_trigger_shell_metacharacters` 和 `test_safe_commands_reject_dangerous_arguments` 是模板。

## 9. `PolicyShellBackend`：host shell 的执行口

停在 [`PolicyShellBackend.execute()`](../src/minicode/backends.py#L18)，因为它是 host shell 的最后一道包装。`evaluate_command()` 返回 `DENY` 时直接构造 `ExecuteResponse`，`exit_code=126`；否则调用 [`super().execute()`](../src/minicode/backends.py#L26)。

文件工具也在这里分叉：[`write()`](../src/minicode/backends.py#L28)、[`edit()`](../src/minicode/backends.py#L35)、[`delete()`](../src/minicode/backends.py#L48) 先看 `allows_file_write()`，`read-only` 返回 permission error，`ask`/`yolo` 继续。

新增一个能执行命令的工具时，要么让它经过这个 backend，要么明确它为什么不需要 policy；否则 hard deny 和 `read-only` 都只是装饰。`tests/test_backends.py` 覆盖了 deny、safe、allow-list 和 read-only 文件拒绝。

## 10. `print_update()` 和 `print_final()`：输出契约

停在 [`print_update()`](../src/minicode/cli.py#L109)，因为工具进度、thinking 和最终回答的分流都在这里。它遍历 update 里的节点，只处理带 `messages` 的字典；AI 消息先打印 thinking，再打印 tool call；tool 消息打印结果；无 tool call 的 AI 消息被记为 `final`。

再停 [`print_final()`](../src/minicode/cli.py#L149)：只有 `output.is_terminal` 才用 `Markdown`，否则按原文打印。这个分支保证管道输出是模型原文。

改输出时同时看 `tests/test_cli.py` 的 `print_update`/`print_final` 用例。`reasoning_text()` 还兼容 `content_blocks`、`summary` 和 `additional_kwargs` 三种 provider 形态；新增模型接入时先确认它落在哪一支。

## 11. `reset_thread()`：清对话，不清工作区

停在 [`reset_thread()`](../src/minicode/cli.py#L260)，因为它是 `/reset`、失败、Ctrl+C 三条路径的共同动作。它从 `config` 取 `thread_id`，调用 checkpointer 的 `delete_thread()`；没有 checkpointer 时什么也不做。

读它时注意：删除的是 thread 的 checkpoint，不是文件。`/reset` 之后模型不记得上一轮，但 workspace 里的改动还在；这一点在 02 的状态表里已经展开。

改 reset 逻辑会影响 REPL 的记忆、并行会话和 SQLite 清理。`tests/test_cli.py` 的 `test_interactive_loop_reset_command`、`test_interactive_loop_resets_thread_after_error` 直接锁这两条路径。

## 12. 评测的 `run_task()` 和 `run_verify()`：第二条入口

停在 [`run_task()`](../src/minicode/evals/runner.py#L296)，因为评测不是“再跑一次 CLI”，而是复制 fixture、开 worker 子进程、再开 verify 子进程。worker 用 `yolo` 和非过滤环境，verify 用 [`verification_env()`](../src/minicode/evals/runner.py#L105) 过滤 provider key。

再停 [`run_verify()`](../src/minicode/evals/runner.py#L142)：hidden tests 被复制到 workspace 之外的 sibling 目录，用 `evals/pytest-safe.ini` 和 `--rootdir`/`--confcutdir` 跑，先 `--collect-only` 再执行。改 fixture 布局、hidden 目录或 verify 命令，先跑 `uv run pytest -q tests/test_evals.py tests/test_evals_cli.py tests/test_evals_worker.py`。

评测的退出码在 [`evals/cli.py`](../src/minicode/evals/cli.py#L70) 单独决定：`bare` 只作为能力下限，单独跑失败也返回 0；`full`/`all` 以非 bare 结果为准。

## 用命令验证你读对了

这些命令在当前 HEAD `2915df5` 上跑过：

```bash
uv run pytest -q tests/test_hitl.py
uv run pytest -q tests/test_policy.py tests/test_backends.py
uv run pytest -q tests/test_evals.py tests/test_evals_cli.py tests/test_evals_worker.py
uv run pytest -q
```

前三条分别覆盖 interrupt/resume、policy/backend、评测隔离；全量那条是 179 passed，2 deselected。`uv run minicode --help` 和 `uv run minicode eval --help` 也跑过，用来确认两个入口的参数没有混在一起。

`tests/test_hitl.py` 不需要 API key：它用 `ToolCallingModel` 驱动真实图，所以适合在没有 provider key 的机器上验证审批路径。

判断规则：如果你能在不打开编辑器的情况下说出“这条路径在哪个 stop、改哪个分支、哪条测试会红”，你就找到了改动点；否则先回到 02 画一遍控制权。
