# 先把边界画出来

判断：MiniCode 是一个把 Deep Agents 图、一个工作区和一层权限策略接起来的最小 CLI；它的价值在边界清楚，不在功能多。你要改的是这条边界上的某个点，不是一座平台。

## 一句话定位

给它一个工作区，模型可以读文件、改文件、跑 shell，直到它给出最终回答。单次任务用 `uv run minicode "fix the failing test"`；在 TTY 下不带 prompt 会进 REPL；任务和会话都通过同一个 `main()` 进入。

入口在 [`pyproject.toml` 的 console script](../pyproject.toml#L22)，转发到 [`main()`](../src/minicode/cli.py#L382)。没有服务端、没有 Web UI、没有多租户、没有自定义工具市场；这些不是还没做，而是当前边界之外的东西。

它也不是“自动修复器”。模型可以跑测试，但 MiniCode 不会在结束时自动验证 workspace；最终回答有没有依据，要你自己看工具输出和 diff。这个边界和“模型可以调用工具”是两件事，读代码时不要混。

## 三个默认值

第一个默认值是模型：`deepseek:deepseek-flash`。`resolve_model()` 的优先级是显式 `--model`、`MINICODE_MODEL`、默认值；空字符串和纯空白会回退，见 [`resolve_model()`](../src/minicode/agent.py#L92)。

第二个默认值是权限：`ask`。文件写入/删除和大多数 shell 命令需要批准；safe 命令直接跑；非 TTY 下 gated action 被拒绝而不是挂起。`--permission-mode read-only|ask|yolo` 可以覆盖，见 [`--permission-mode` 的默认值](../src/minicode/cli.py#L343)。

第三个默认值是 thread：`default`。单次任务也有 `thread_id`，但只有 REPL 会把它持久化到 SQLite；`--thread`/`--db` 与 prompt 同时出现会报错，见 [`main()` 的检查](../src/minicode/cli.py#L403)。

这三个值合起来决定了你第一次运行时的体验：默认模型能不能用、默认权限会不会打断你、默认会话能不能续。排障时先确认这三个，不要一上来读图。

## 主线请求里会发生什么

`uv run minicode "fix the failing test"` 最可能先调用 `read_file`/`grep` 看代码，再调用 `edit_file` 修改，再调用 `execute` 跑测试。`read_file` 和 `grep` 不经过 `interrupt_on`；`edit_file` 在 `ask` 下会暂停等人批准；`execute` 要看具体命令。

这里有一个容易误判的点：`uv run pytest` 不在 safe list 里。safe list 只有 `uv --version` 这类版本命令，见 [`SAFE_COMMAND_PREFIXES`](../src/minicode/policy.py#L42)。所以在默认 `ask` 下，agent 跑测试会要求批准；`git status`、`git diff`、`ls`、`cat` 则不会。

如果你在 `read-only` 下跑同一条主线，`uv run pytest` 会被直接拒绝，因为 `read-only` 只允许 safe 命令；模型能看到拒绝原因，但它不能跑测试。这个模式适合“只读审查”，不适合“修完再验证”。

## 最短可运行路径

完整闭环只有七步：

1. `main()` 解析 prompt，读 `.env` 里的模型和 provider key，决定单次任务还是 REPL。
2. `main()` 生成 `thread_id`，调用 [`build_agent()`](../src/minicode/agent.py#L132)。
3. `build_agent()` 创建 `Policy` 和 `PolicyShellBackend`，按 `ask` 模式挂 `interrupt_on`，建图。
4. [`run_turn()`](../src/minicode/cli.py#L224) 把用户消息送进图；模型返回 tool call 或最终回答。
5. 如果是 `ask` 且 tool call 被 gate，CLI 暂停等人批准；批准后 `Command(resume=...)` 回到图里。
6. 工具节点调用 [`PolicyShellBackend.execute()`](../src/minicode/backends.py#L18) 或文件工具；结果作为 tool 消息回到模型。
7. 最终那条无 tool call 的 AI 消息由 [`print_final()`](../src/minicode/cli.py#L149) 写到 stdout；工具进度走 stderr。

“最短闭环”的终点不是进程退出，而是模型不再调用工具。到了这一步，`run_turn()` 返回最终那条 AI 消息，`main()` 打印并返回 0；如果模型还在调用工具，循环继续。

`ask` 模式下即使没有 TTY，也不会挂住：gated action 会被拒绝，模型收到拒绝原因后继续，见 [`ask_approval()`](../src/minicode/cli.py#L184)。所以 `echo "fix it" | minicode` 可能以 0 退出，但并没有执行任何写操作；不要把“退出码 0”当成“任务完成”。

单次任务的失败出口也要记住：普通异常返回 1，`KeyboardInterrupt` 返回 130，`--debug` 直接抛 traceback。REPL 则把失败或 Ctrl+C 变成“清掉当前 thread，继续下一条输入”。这些行为都在 [`main()` 的异常处理](../src/minicode/cli.py#L449) 和 [`interactive_loop()`](../src/minicode/cli.py#L299) 里。

## 什么算完成，什么不算

算完成的最低条件：模型返回一条无 tool call 的 AI 消息，`run_turn()` 把它交给 `print_final()`，进程返回 0。工具调用和文件改动不是完成条件；模型可以在没有改任何东西的情况下给出最终回答。

不算完成的情况：模型还在调用工具、gated action 被拒绝后模型只解释不继续、进程因异常返回 1、或者你在非 TTY 下看到拒绝但忽略了。判断“任务有没有真的做成”，要看工具输出和 workspace，不要只看结尾那段文字。

## 刻意不做的事

**不做 sandbox。** `LocalShellBackend` 在 host 上以你的用户权限执行命令；MiniCode 只在外面包了 `PolicyShellBackend`。`read-only`、`ask`、`yolo` 和 hard deny 都是 guardrail，不是内核级隔离。这个边界写在 [`PolicyShellBackend.execute()`](../src/minicode/backends.py#L18) 和 README 的 Safety 段里。

**不维护一套自定义工具。** 文件工具、shell、计划和子 agent 都来自 Deep Agents；MiniCode 只负责 backend 和权限。要加一个“能执行命令”的工具，先决定它是否经过 `PolicyShellBackend`，否则它会绕过所有模式。

**不做通用 benchmark。** `evals/` 是 20 个自包含 fixture 的 smoke suite，用来回答“这次改动有没有把已知任务弄坏”，不是“模型会不会写任意仓库”。验证是约定级隔离，不是对抗性 sandbox；这个限制在 [`evals/README.md`](../evals/README.md) 和 PR #7 的审阅里都写了。

**不做完整 shell 解析器。** `Policy` 用引号感知的 segment/token 启发式，不是 AST。它能挡住常见灾难命令和明显的元字符绕过，但 `time -p`、`nice`、`timeout`、`xargs` 这类包装仍有缺口；把它当 sandbox 会高估安全性。

**不做 provider 抽象层。** 模型通过 LangChain 的 `init_chat_model`/`create_deep_agent` 接入，默认 DeepSeek；换 provider 要加对应的 LangChain 集成包。MiniCode 不维护统一的能力矩阵，也不保证每个 provider 的 reasoning/tool call 形态一致。

**审计日志仍在计划中。** 当前 HEAD 没有 `audit.py`/`redaction.py`；PR #16 是未合入的补充。读文档时不要把“计划中的审计”当成现状。

## 最危险的一条边界

最危险的不是“模型会不会说错”，而是 `execute` 真的会在你的机器上跑。`read-only` 只表示“不改状态”，不表示“读不到东西”：`cat ~/.ssh/id_rsa` 仍然命中 `cat` 的 safe 前缀，在 `read-only` 下也是 ALLOW。这个结论可以直接用 [`_is_safe()`](../src/minicode/policy.py#L457) 和 [`SAFE_COMMAND_PREFIXES`](../src/minicode/policy.py#L42) 复现。

`yolo` 也不是“没有策略”。它跳过 HITL，但 [`evaluate_command()`](../src/minicode/policy.py#L413) 仍然先跑 hard deny；`rm -rf /`、`git push --force` 这类命令在 yolo 下仍然返回 126。真正的风险在 hard deny 覆盖不到的命令：包装器、参数组合、从网络拉下来的脚本。

评测的 hidden tests 也不是安全边界。它们被放在 workspace 之外，用独立 pytest 配置跑，这是为了防止 agent 用 `pytest.ini`/`conftest.py` 让可见测试假通过；它不防一个有 shell 权限的 agent 通过绝对路径或进程信息找到它们。用不可信代码跑 eval，仍然要容器或 VM。

所以，改权限相关代码时先写清楚三件事：这条命令在哪个模式会被 gate、被拒绝时模型收到什么、hard deny 是否在 yolo 之前。三件事说不清，就不要把“read-only”或“yolo”当成安全承诺。

## 边界上的三个判断

第一个判断：这个改动会不会让某条 tool call 更容易落地？如果会，先看 `Policy`、`interrupt_on` 和 `PolicyShellBackend` 三处，而不是先改 CLI 文案。权限改动的最小验证是三条命令：read-only 该拒、ask 该问、yolo 该放但 hard deny 仍拦。

第二个判断：这个改动会不会改变状态活多久？单次 `ask` 需要 `InMemorySaver` 才能 resume；REPL 需要 SQLite 才能跨进程。把这两件事混在一起，通常会出现“单次任务留下数据库”或“REPL 重启后失忆”。

第三个判断：这个改动会不会改变 stdout/stderr 契约？最终答案在 stdout，进度和 thinking 在 stderr；Markdown 只在 TTY 渲染。改输出时先跑管道，不要只在终端里看。

## 一个具体判断练习

假设 PR 加了一个 `run_shell` 工具，函数体直接 `subprocess.run`。它看起来像工具变更，实际是权限变更：它绕过了 `PolicyShellBackend.execute()`。正确做法是复用 backend，或者明确它为什么不需要 policy。

反过来，假设 PR 只是把 `print_final()` 的 Markdown 换成纯文本，它不该动 `Policy`。把展示变更和权限变更分开审，能避免“为了改输出而放宽审批”的连锁反应。

## 排障入口

如果 agent 没有执行你期待的命令，先在 stderr 找 `approval required`，再确认当前 `--permission-mode`。默认 `ask` 下，`uv run pytest` 这种不在 safe list 的命令会停下来等人；非 TTY 下则直接拒绝。

如果 REPL 不记得上一轮，先确认两次启动用了同一个 `--thread` 和 `--db`，再看有没有触发 `/reset`、失败或 Ctrl+C。后三者都会删除当前 thread。

如果管道输出里混进了进度，先看 [`main()` 的两个 Console](../src/minicode/cli.py#L393)：`progress` 是 stderr，`output` 是 stdout。Markdown 渲染只在 `output.is_terminal` 时发生。

如果 eval 结果和本地不一致，先确认 `--baseline`、`--task` 和 `MINICODE_EVALS_DIR`。`bare` 只作为能力下限，单独跑失败也返回 0；`full`/`all` 才用非 bare 结果决定退出码。

## 第一次读的顺序

如果你现在就要改权限，先读 02 的 interrupt 段，再读 04 的 stop 4、7、9；再用 05 的问题清单审自己的 diff。03 的决策 2、3、5 解释为什么是这三段，不是一段。

如果你要加工具或换 backend，先读 04 的 stop 3 和 stop 9，再读 03 的决策 1、2。重点是“新工具是否经过 `PolicyShellBackend`”，而不是工具函数本身。

如果你要跑评测或加 fixture，先读 04 的 stop 12，再读 03 的决策 6。先跑单任务，再跑 smoke；不要把 20/20 当成通用能力。

## 哪些需求不属于这里

如果需求是“给 agent 加一个 Web 界面”“支持多用户会话”“把审批做成团队工作流”，它需要新的服务层和身份层，不是改 `cli.py` 能解决的。先另起项目，或者明确它是一个新边界。

如果需求是“让 read-only 绝对读不到 workspace 外的文件”，它需要 OS 级隔离或容器，不是再加几条 `Policy` 规则。当前的 `Policy` 只分类 shell 命令，不限制 `cat` 的读取范围。

如果需求是“让 eval 防住恶意 agent”，它需要沙箱、网络隔离和资源限制，不是把 hidden tests 再挪远一点。看清这一点，才不会把 guardrail 的测试当成安全测试。

判断规则：如果一个改动需要你用“这不会真的执行”来解释，先检查它是否经过 `PolicyShellBackend`；如果没有，它就不是权限改动，而是新的执行入口。

边界不是功能列表，是执行入口和状态的归属。功能可以慢慢加，边界一旦漏了，后面的审批和测试都补不回来。
