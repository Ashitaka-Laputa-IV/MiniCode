# 七个已经付过代价的选择

判断：MiniCode 的功能不多，真正的设计都在约束里。下面七个选择都能在代码、测试或 PR 里找到代价；读的时候不要问“为什么不做大”，要问“这个代价现在由谁承担”。

## 1. 用 Deep Agents，而不是自己搭图

**问题**：一个最小 coding agent 要不要自己写模型循环、文件工具、shell 工具和子 agent？

**约束**：需要文件读写、shell、计划和子 agent；Python 3.13；CLI 是唯一入口，不能引入服务端组件。

**选项**：自己写 LangGraph 节点和工具；只暴露一个 shell 工具；用 Deep Agents 的 `create_deep_agent()` 加自定义 backend。

**选择**：用 Deep Agents。`build_agent()` 只负责装配模型、backend、interrupt 和 checkpointer，模型循环、工具节点和中间件由 harness 提供，见 [`build_agent()`](../src/minicode/agent.py#L132)。

**代价**：受 `deepagents` 版本和中间件顺序约束；工具名、图节点名、虚拟文件系统语义都来自上游。升级依赖时，`interrupt_on` 和 `stream_mode="updates"` 的行为可能先变，项目代码不一定变。

**何时重审**：需要完全自定义工具契约、需要换掉 harness 的模型循环、或者 `deepagents` 出现破坏性升级时。

**证据**：`pyproject.toml` 直接依赖 `deepagents>=0.7.34`，见 [`dependencies`](../pyproject.toml#L10)；`SYSTEM_PROMPT` 专门解释虚拟文件系统，见 [`SYSTEM_PROMPT`](../src/minicode/agent.py#L64)；PR #2 的说明是“基于 Deep Agents `create_deep_agent` 实现最小 code agent”。为什么没有自己搭图，PR #2 没有记录候选方案对比，不能补故事。

## 2. 权限拆成 Policy、HITL 和 backend 三段

**问题**：`read-only`/`ask`/`yolo` 怎么才能真正约束一次 tool call，而不是只写在文档里？

**约束**：`LocalShellBackend` 实现的是 `SandboxBackendProtocol`；Deep Agents 的 `FilesystemPermission` 与带执行能力的 backend 不兼容，会抛 `NotImplementedError`。shell 工具一旦执行，就在 host 上以用户权限运行。

**选项**：只用 Deep Agents 的文件 permissions；只靠 system prompt 提醒模型；在 middleware 里拦截；在 backend 外包一层 policy，再用 HITL 处理需要人决定的部分。

**选择**：三段式。`Policy` 做命令分类，[`build_agent()` 的 `interrupt_on`](../src/minicode/agent.py#L159) 把 `ask` 的 tool call 暂停，[`PolicyShellBackend`](../src/minicode/backends.py#L11) 在真正执行前再做一次 deny/allow 判断。

**代价**：分类逻辑有两个调用点（`needs_shell_approval()` 和 `PolicyShellBackend.execute()`），改规则时容易只改一处；hard deny 是有限集合，不是完整 shell 解析器；新增一个绕过 backend 的执行工具，就等于绕过所有模式。

**何时重审**：新增文件/shell 工具、Deep Agents 支持在 shell backend 上做 permissions、或者需要把不可信任务放进同一进程时。

**证据**：`interrupt_on` 只覆盖 `write_file`/`edit_file`/`delete`/`execute`，见 [`build_agent()` 的中断配置](../src/minicode/agent.py#L166)；backend 的 deny 在 [`execute()`](../src/minicode/backends.py#L18)，文件写入在 [`write()`](../src/minicode/backends.py#L28)；PR #15 的“关键设计”明确记录了 `FilesystemPermission` 不兼容。

## 3. 默认 `ask`，非 TTY 直接拒绝

**问题**：默认权限模式应该偏安全还是偏自动？没有交互终端时怎么办？

**约束**：agent 能改文件、跑 shell；CI 和 eval 是非交互环境；用户也会用管道把 prompt 喂进来。

**选项**：默认 `yolo`，少打断；默认 `read-only`，最安全但几乎不能干活；默认 `ask`，把决定推给人；默认 `ask` 但在非 TTY 下阻塞等待。

**选择**：默认 `ask`；非 TTY 时不阻塞，直接 reject，并把原因写进 rejection message。自动执行必须显式 `--permission-mode yolo` 或给自己信任的命令加 allow-list。eval worker 在自己的子进程里显式用 `yolo`。

**代价**：`echo "fix it" | minicode` 这类用法不再“自动跑”；被 gate 的 action 会被拒绝，模型会收到拒绝并决定重试或解释。用户如果没意识到默认模式，会把拒绝当成模型失败。

**何时重审**：非交互使用变成主路径、审批 UI 支持更细的决定、或者有安全的默认 allow-list 能覆盖常见测试命令时。

**证据**：CLI 默认值是 `PermissionMode.ASK`，见 [`--permission-mode` 的默认值](../src/minicode/cli.py#L343)；非 TTY 的 reject 在 [`ask_approval()`](../src/minicode/cli.py#L184)；eval worker 的 `yolo` 在 [`run_full()`](../src/minicode/evals/worker.py#L70)；PR #15 的“注意”写明“默认 `ask` 会改变非 TTY one-shot 行为”。

## 4. checkpointer 按运行方式拆开

**问题**：对话状态存在哪里，活多久？

**约束**：`ask` 的 interrupt/resume 必须有 checkpointer；REPL 需要跨进程继续；单次任务不应该在工作区里留数据库；SQLite 适合单进程轻量场景。

**选项**：所有路径都用 SQLite；所有路径都用内存；单次任务完全不要 checkpointer；按运行方式拆。

**选择**：按运行方式拆。单次 `ask` 用 `InMemorySaver`，REPL 用 `SqliteSaver`，单次 `read-only`/`yolo` 不挂 checkpointer；`--db`/`--thread` 只在 REPL 生效。分支在 [`build_agent()`](../src/minicode/agent.py#L181)。

**代价**：单次 `ask` 的状态活不过进程；REPL 的 SQLite 有并发限制，同一 workspace 的并行实例要显式用不同 `--thread`/`--db`；库调用者开 `checkpoint=True` 后要自己关闭连接。

**何时重审**：需要单次任务断点续跑、需要多进程共享同一会话、或者换掉 SQLite 时。

**证据**：`main()` 用 `checkpoint=not bool(prompt)` 区分单次和 REPL，见 [`main()` 的 checkpoint 参数](../src/minicode/cli.py#L422)；`--db`/`--thread` 与 prompt 冲突的检查在 [`main()`](../src/minicode/cli.py#L403)；跨 agent 实例的持久化测试在 [`test_sqlite.py`](../tests/test_sqlite.py#L37)。

## 5. shell 策略用引号感知的 segment/token 启发式

**问题**：怎么在不写完整 shell 解析器、也不做 sandbox 的前提下，判断一条命令是 safe、network、mutating 还是 hard deny？

**约束**：要同时面对 Windows `cmd` 和 POSIX shell；引号内的字面量不应触发元字符；`bash -c '...'` 的 payload 不能被简单切开；safe 命令也可能带危险参数。

**选项**：对整条字符串做正则；用 shell AST 解析；按 segment/token 做启发式；只维护一个 hard deny 列表。

**选择**：启发式。`_syntax_view()` 去掉引号字面量但保留 `$`/反引号展开，见 [`_syntax_view()`](../src/minicode/policy.py#L200)；`_split_segments()` 做引号感知切分，见 [`_split_segments()`](../src/minicode/policy.py#L158)；`_segment_hard_denied()` 剥离 `sudo`/`env`/`shell -c` 等前缀后再判；`_is_safe()` 用安全前缀加危险参数拒绝。

**代价**：它不是完整解析器。`_strip_prefixes()` 只剥裸 `time`，`time -p rm -rf /` 在 `yolo` 下仍会放行；`nice`、`timeout`、`xargs` 也不在剥离列表里。引号、转义、Windows 路径都可能有边界。安全判断因此只能当 guardrail，不能当 sandbox。

**何时重审**：发现新的绕过、增加新的 shell 方言、或者需要把“审批”提升为“隔离”时。

**证据**：三段实现分别在 [`_syntax_view()`](../src/minicode/policy.py#L200)、[`_split_segments()`](../src/minicode/policy.py#L158)、[`_segment_hard_denied()`](../src/minicode/policy.py#L325)；引号字面量的回归测试在 [`test_policy.py`](../tests/test_policy.py#L157)；wrapper 的回归测试在 [`test_policy.py`](../tests/test_policy.py#L181)；PR #15 的复审记录明确写了“wrapper 剥离是在 segment 切分之后做的”以及后续修复。

## 6. 评测用 fixture + hidden tests，不用 LLM judge

**问题**：怎么判断 agent 真的修好了一个仓库，而不是“看起来改了”？

**约束**：任务要离线、可重复、成本可控；agent 可能改 `pytest.ini`/`conftest.py` 来让可见测试通过；验证阶段不应该拿到 provider key；单任务失败不能中断整个 suite。

**选项**：让 LLM 当裁判；只跑 fixture 里的可见测试；把 hidden tests 放进 workspace；把 hidden tests 放到 workspace 外，用独立 pytest 配置跑。

**选择**：fixture 复制到临时目录，worker 子进程跑 agent，verify 子进程跑 hidden tests；hidden tests 放在 workspace 的 sibling 目录，用 `evals/pytest-safe.ini`、`--rootdir`、`--confcutdir` 和 `--collect-only` 守卫。`bare` baseline 只把 prompt 直接发给模型，作为能力下限。

**代价**：这是约定级隔离，不是对抗性 sandbox；agent 仍可能通过 shell 或绝对路径找到 hidden tests。`add-tests-*` 仍有文本启发式，20/20 也只代表 smoke suite。验证和 worker 的 timeout 分开后，单任务最坏耗时仍接近两段之和。

**何时重审**：要跑不可信代码、要扩大 benchmark、或者要把 hidden tests 当成真正的隔离边界时。

**证据**：hidden tests 的外置和 safe ini 在 [`run_verify()`](../src/minicode/evals/runner.py#L142)；验证环境过滤在 [`verification_env()`](../src/minicode/evals/runner.py#L105)；单任务容错在 [`run_suite()`](../src/minicode/evals/runner.py#L391)；`bare` 的退出码在 [`evals/cli.py`](../src/minicode/evals/cli.py#L70)；PR #7 的审阅记录了“验证隔离是 convention-level”。

## 7. stdout 只放最终答案，进度走 stderr

**问题**：CLI 既要给人看，又要能被管道和脚本消费，输出怎么分？

**约束**：Rich 的 Markdown 渲染会改变文本；工具名和参数来自模型，可能包含 markup；reasoning 的形态随 provider 变；管道里不应该出现进度噪音。

**选项**：所有内容都走 stdout；所有内容都走 stderr；最终答案 stdout、进度/thinking stderr；始终用 Markdown 渲染。

**选择**：最终答案走 `output`（stdout），工具进度和 thinking 走 `progress`（stderr）；`print_final()` 只在 `output.is_terminal` 为真时渲染 Markdown，否则按原文打印。见 [`main()` 的两个 Console](../src/minicode/cli.py#L393) 和 [`print_final()`](../src/minicode/cli.py#L149)。

**代价**：两个流的顺序在终端里可能交错；reasoning 提取要兼容 `content_blocks`、`summary` 和 `additional_kwargs` 三种形态；`--no-thinking` 只能关显示，不能阻止模型产生 reasoning token。

**何时重审**：需要机器可读输出（例如 JSON mode）、新增 provider 的 reasoning 结构、或者要把 CLI 嵌进别的 UI 时。

**证据**：`print_update()` 把 thinking 和 tool 活动写到 `progress`，见 [`print_update()`](../src/minicode/cli.py#L109)；`print_final()` 的 TTY 分支在 [`print_final()`](../src/minicode/cli.py#L152)；非终端原文输出的测试在 [`test_cli.py`](../tests/test_cli.py#L188)；PR #4 的审阅明确要求“管道/重定向时不要渲染 Markdown”。

判断规则：新需求如果改变“哪些 tool call 会落地”，先看决策 2、3、5；如果只改变“怎么显示”，先看决策 7；如果改变“怎么证明它做对了”，先看决策 6。选错决策层，代码会越改越像补丁。

这些决策不是永久结论。代码和测试是事实来源；如果你发现实现已经偏离某条“选择”，先把偏离写进 PR，再决定是改代码还是改决策。

