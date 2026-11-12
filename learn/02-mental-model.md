# 心智模型

## 先记住三层

```text
用户输入
  |
  v
CLI 层（cli.py）          怎么运行、怎么显示、怎么审批
  |
  v
Agent 层（agent.py）      用什么模型、什么 backend、什么 checkpointer、什么 interrupt
  |
  v
策略层（policy.py / backends.py）  哪些命令能跑、哪些必须拦、哪些要审批
  |
  v
Deep Agents / LangGraph   工具循环、文件工具、shell、子 agent、状态图
```

`evals/` 是另一条独立链路：它不经过 REPL，而是启动子进程跑任务，再用可执行验证判断成败。

## 一张总图

```text
用户
  |
  | prompt / REPL 输入
  v
cli.main()
  |-- build_parser()              解析 --model / --root / --permission-mode / --db ...
  |-- load_env()                  只应用 .env 中的模型和 provider key
  |
  v
agent.build_agent()
  |-- resolve_root()              workspace 必须是已存在目录
  |-- resolve_model()             CLI > MINICODE_MODEL > deepseek:deepseek-flash
  |-- Policy(...)                 read-only / ask / yolo
  |-- shell_env()                 过滤环境变量，不把 provider key 给 shell
  |-- PolicyShellBackend(...)     LocalShellBackend + 策略拦截
  |-- interrupt_on=...            ask 模式：文件/命令审批
  |-- checkpointer=...            SQLite（REPL）或 InMemory（ask 单次）
  |
  v
Deep Agents graph（LangGraph）
  |-- 规划 / todo
  |-- 文件工具：ls / read_file / write_file / edit_file / glob / grep
  |-- execute：调用 PolicyShellBackend
  |-- task：子 agent
  |-- summarization：长上下文压缩
  |
  v
stream_mode="updates"
  |-- print_update()               stderr：thinking、tool call、tool result
  |-- 检测 __interrupt__           ask 模式审批
  |-- resume_command()             approve/reject 后继续
  |
  v
最后一个 AI message
  |
  v
print_final()                      stdout：TTY 下 Markdown，管道下原文
```

## 两条运行路径

### 1. 单次任务

```text
main()
  -> prompt = "fix tests"
  -> build_agent(checkpoint=False)
       -> 如果 permission_mode == ask，仍然创建 InMemorySaver
  -> config = make_config("default")
  -> run_turn(prompt)
       -> agent.stream(...)
       -> 如果中断，ask_approval() 后 Command(resume=...)
  -> print_final()
  -> close_checkpointer()
  -> exit 0/1
```

单次任务不写入 SQLite，也不跨进程保留会话。但 `ask` 模式仍然需要 checkpointer 来支撑 LangGraph 的 interrupt/resume，所以它使用的是进程内的 `InMemorySaver`，不是「完全没有状态」。

### 2. REPL

```text
main()
  -> build_agent(checkpoint=True)
       -> SqliteSaver(<root>/.minicode/checkpoints.sqlite)
  -> config = make_config(thread_id)
  -> interactive_loop()
       -> output.input("minicode> ")
       -> /help /reset /exit
       -> run_turn(prompt)
       -> print_final()
       -> 下一轮
```

REPL 的 `thread_id` 默认是 `default`：

- `--thread work` 选择另一个会话；
- `--db state.sqlite` 选择另一个数据库文件；
- 同一个 workspace 并行跑多个 REPL 时，必须使用不同 `--thread` 或 `--db`，否则会 `database is locked` 或 checkpoint 交错。

`/reset`、单轮异常、Ctrl+C 会调用 `reset_thread()`：删除当前 thread 的 checkpoint，但保留 thread id。下一轮从空上下文开始。这样不会恢复上一轮未完成的图节点，避免重复执行 shell。

## HITL 审批状态机

`ask` 模式下，工具调用不是直接执行，而是经过一层 interrupt：

```text
模型发出 tool_call
  |
  v
interrupt_on 判断
  |-- write_file / edit_file / delete：总是中断
  |-- execute：只有 policy.needs_approval(command) 为真才中断
  |-- 其他工具：不中断
  |
  v
LangGraph 产生 __interrupt__
  |
  v
cli.run_turn() 收集 interrupt
  |
  v
ask_approval()
  |-- 显示工具名、description、参数
  |-- TTY：等待 y/N
  |-- 非 TTY：直接 reject，绝不阻塞
  |
  v
Command(resume={"decisions": [...]})
  |-- approve：工具继续执行
  |-- reject：工具不执行，模型收到 rejection message
  |
  v
继续 stream，直到没有新的 interrupt
```

几个容易混淆的点：

1. **interrupt 是 LangGraph 的能力，不是 backend 的能力**。`PolicyShellBackend` 只负责最后的 hard deny 和 read-only 文件拒绝。
2. **approve 不等于绕过 hard deny**。用户批准后，命令仍会走 `PolicyShellBackend.execute()`；hard deny 仍然返回 exit code 126。
3. **单次任务也能审批**。因为 `build_agent()` 在 `ask` 模式自动加了 `InMemorySaver`。
4. **非 TTY 不会挂起**。这是「fail closed」：需要审批的动作直接拒绝，并给出重新运行的建议。
5. **多中断**：`resume_command()` 对多个 interrupt 使用 `{interrupt.id: {"decisions": ...}}`；单个 interrupt 使用简单的 `{"decisions": [...]}`。

## 策略判定流程

`Policy.evaluate_command()` 的顺序很重要：

```text
命令
  |
  v
空命令？ -> DENY
  |
  v
hard deny？ -> DENY（所有模式都生效）
  |
  v
yolo？ -> ALLOW
  |
  v
allow-list 包含 all 且不是 read-only？ -> ALLOW
  |
  v
safe 命令？ -> ALLOW
  |
  v
分类：network / mutating / unknown
  |
  +-- read-only：DENY（网络 / 变更 / 非 safe）
  +-- ask：ASK（网络 / 变更 / 未知）
  +-- yolo：前面已经 ALLOW
```

几个关键细节：

- **hard deny 永远优先**，`yolo` 也不能执行 `rm -rf /`、`git push --force`、`curl | sh` 等。
- **safe 命令不是「字符串前缀匹配」那么简单**：`_is_safe()` 会先看引号外的 shell 元字符、重定向、危险参数，再按 segment 匹配 allow-list。
- **`read-only` 不只是拦截文件工具**：shell 也会拒绝网络、变更和未知命令。
- **`ask` 模式中，safe 命令直接跑，网络/变更/未知命令才弹审批**。
- **`allow-list=all` 在 read-only 下不生效**；这是刻意的。
- **`recommended` 目前就是内置 safe 列表**，不会额外放宽。
- **backend 是最后一道兜底**：即使调用方绕过 HITL，`PolicyShellBackend` 仍会拒绝 hard deny 和 read-only 文件写入。

## 工具模型

Deep Agents 默认提供：

- 文件：`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`
- 执行：`execute`
- 委派：`task`

MiniCode 没有重写这些工具，而是：

- 用 `PolicyShellBackend` 决定文件根目录、shell 行为和拦截；
- 用 `SYSTEM_PROMPT` 告诉模型路径语义和行为边界；
- 用 `interrupt_on` 在 ask 模式接审批。

### 路径语义

文件工具使用**虚拟文件系统**：

```text
/                     -> workspace 根
/src/minicode/cli.py  -> <workspace>/src/minicode/cli.py
```

不要给文件工具传 `C:\...`。Windows 盘符路径会被拒绝。

Shell 命令不同：它在 workspace 根目录下启动，使用相对路径，Windows 下是 `cmd.exe`。

## 配置边界

有两条独立的 allowlist，不要混淆：

### `.env` 加载 allowlist

`cli.load_env()` 只应用：

- `MINICODE_MODEL`
- 已知 provider API key

它会忽略 `OPENAI_BASE_URL`、`*_API_BASE`、endpoint 类变量，避免陌生仓库的 `.env` 把 key 重定向到其他地址。shell 中已有变量优先，空值和纯空白值会被忽略。

`MINICODE_PERMISSION_MODE` 和 `MINICODE_SHELL_ALLOW_LIST` 只从 shell 环境读取，不从 `.env` 读取；这是有意的安全边界。

### shell 继承 allowlist

`agent.shell_env()` 只把 PATH、Windows 系统变量、Python/uv 相关变量传给 `execute` 子进程。

因此：

- shell 能运行 `uv`、`git`、`python` 等命令；
- shell 里拿不到 `DEEPSEEK_API_KEY` 等 provider key。

## 输出模型

| 通道 | 内容 | 目的 |
| --- | --- | --- |
| stdout | 最终回答 | 可被管道/重定向消费 |
| stderr | `thinking`、`-> tool`、`<- tool`、错误、进度 | 不污染最终文本 |
| TTY stdout | Rich Markdown | 人类阅读 |
| 非 TTY stdout | 原始文本 | `> notes.md`、`| grep` 保持模型原文 |

`print_final()` 是这条边界的唯一实现点。`print_update()` 负责过程输出，并返回最后一个 AI message。

## 评测流程

`minicode eval` 是另一条执行路径：

```text
evals/cli.py
  -> load_suite("smoke")
  -> 复制 fixture 到临时 workspace
  -> 启动子进程 minicode.evals.worker
       -> full：build_agent(permission_mode="yolo", checkpoint=False)
       -> bare：init_chat_model(...).invoke(prompt)
  -> worker 写 JSON 结果
  -> runner 在隔离环境里跑验证
       -> hidden tests 或 verify_command / verify.py
  -> 汇总 pass@1、tool calls、tokens、cost、duration
  -> 写 JSON 报告（--json）
```

关键边界：

- **worker 环境**包含 provider key，因为要调用模型；
- **验证环境**使用 `shell_env()`，不包含 provider key；
- hidden tests 不复制进 agent 的 workspace，而是放到同级目录，验证时才用；
- 验证不是 LLM judge，而是 pytest / 脚本的退出码；
- `full` 有工具，`bare` 没有工具；`bare` 失败是预期信息，不作为 CI 失败。

## 失败模型

- 缺 API key：`print_error()` 输出一行明确提示，退出码 1。
- `--root` 不存在：`resolve_root()` 抛 `ValueError`，CLI 捕获并输出。
- 单轮异常：单次任务返回 1；REPL 打印错误、重置 thread、继续下一轮。
- Ctrl+C：单次任务返回 130；REPL 重置 thread、继续。
- `--debug`：不吞异常，直接抛出完整 traceback。
- SQLite 并行：不同 `--thread` / `--db` 隔离；否则可能 `database is locked`。

## 安全边界

当前实现的边界是：

1. workspace 根目录限制文件工具的虚拟路径；
2. shell 环境变量过滤；
3. safe allow-list / network / mutating 分类；
4. hard deny-list；
5. ask 模式的 HITL 审批；
6. read-only 模式的文件和 shell 拒绝。

它**没有**：

1. 文件/网络/进程沙箱；
2. OS 级权限隔离；
3. 资源限制；
4. 对自定义 secret 的完整识别（审计/脱敏仍在开放 PR #16）。

所以正确的心智模型是：**一个受策略和审批约束的本地开发助手，不是安全执行环境。** prompt 里的「谨慎」只是建议，真正的拦截在 policy/backend/HITL。

## 记住这几条

- `cli.py` 负责「怎么运行」，`agent.py` 负责「运行什么」，`policy.py` 负责「什么能做」。
- 单次任务 `ask` 也有 checkpointer，但只在内存里；REPL 才用 SQLite。
- `reset_thread()` 删除当前 thread，不换新 id。
- 文件路径是虚拟的，shell 路径是相对的。
- hard deny 在 yolo 下仍然生效。
- 非 TTY 的审批是拒绝，不是等待。
- `full` 评测走 agent，`bare` 评测只问模型；验证环境不继承 provider key。
