# 代码导读

## 推荐阅读顺序

```text
pyproject.toml
  -> src/minicode/__init__.py / __main__.py
  -> src/minicode/cli.py（先看 main）
  -> src/minicode/agent.py
  -> src/minicode/policy.py
  -> src/minicode/backends.py
  -> src/minicode/evals/cli.py
  -> src/minicode/evals/runner.py / worker.py
  -> tests/test_policy.py
  -> tests/test_hitl.py
  -> tests/test_cli.py / test_agent.py
  -> tests/test_evals*.py
```

先看入口和调用链，再看策略与测试。`evals/` 可以最后看，它不影响 CLI 主路径。

### 读 `cli.py` 时不要按行号顺序

文件里的定义顺序是：

```text
load_env
message_text
reasoning_text
short_json
print_update
print_final
print_error
ask_approval
resume_command
run_turn
make_config / reset_thread
interactive_loop
build_parser
main
```

但执行顺序不是这样。建议按调用链读：

```text
main
  -> build_parser / load_env
  -> build_agent
  -> run_turn
       -> print_update
       -> resume_command -> ask_approval
  -> interactive_loop
       -> run_turn
  -> print_final / print_error
  -> close_checkpointer
```

助手函数放在 `main` 前面只是 Python 文件的常见组织方式，不代表它们是入口。**先读 `main`，再顺着它调用的函数往下读。**

## 入口层

### `pyproject.toml`

```toml
[project.scripts]
minicode = "minicode:main"
```

安装后 `minicode` 命令实际调用 `minicode.__init__.main`。

### `src/minicode/__init__.py`

```python
from .cli import main

__all__ = ["main"]
```

只做导出，不放逻辑。

### `src/minicode/__main__.py`

```python
from minicode import main

if __name__ == "__main__":
    raise SystemExit(main())
```

`raise SystemExit(main())` 是关键：`python -m minicode` 的退出码必须反映 `main()` 的返回值。

## 一次单任务执行

```text
minicode "fix tests"
  |
  v
cli.main()
  |-- build_parser().parse_args()
  |-- load_env()
  |-- prompt 校验 / 从 stdin 读取
  |-- build_agent(checkpoint=False)
  |-- run_turn()
  |     |-- agent.stream(..., stream_mode="updates")
  |     |-- print_update() -> stderr
  |     |-- __interrupt__ -> ask_approval() -> Command(resume=...)
  |     `-- 返回最后一个 AI message
  |-- print_final() -> stdout
  |-- close_checkpointer()
  `-- return 0 / 1
```

### `main()` 的关键分支

1. `argv[0] == "eval"` -> 交给 `minicode.evals.cli.main`，不进入普通 CLI。
2. `prompt and args.interactive` -> 参数错误。
3. 无 prompt、非交互、非 TTY -> 从 stdin 读 prompt。
4. 有 prompt 但带 `--db` / `--thread` -> 参数错误（SQLite 选项只给 REPL）。
5. 有 prompt -> 单次任务。
6. 无 prompt -> `interactive_loop()`。

`--debug` 只影响：

- 是否打印 env 路径、workspace、model、thread；
- 异常是否直接抛出完整 traceback。

## 一次 REPL 执行

```text
main()
  |-- build_agent(checkpoint=True)
  |     `-- SqliteSaver(<root>/.minicode/checkpoints.sqlite)
  |-- config = make_config(thread_id)
  `-- interactive_loop()
        |
        |-- output.input("minicode> ")
        |
        |-- /help  -> 打印命令
        |-- /reset -> reset_thread()
        |-- /exit  -> 返回 0
        |
        `-- run_turn()
              |-- agent.stream(..., config=config)
              |-- print_update() -> stderr
              |-- __interrupt__ -> 审批
              `-- print_final() -> stdout
```

### thread 生命周期

- `make_config(thread_id)`：`{"configurable": {"thread_id": thread_id}}`。
- 默认 thread：`default`。
- `--thread work`：换会话；`--db state.sqlite`：换数据库。
- `reset_thread(config, agent)`：调用 `checkpointer.delete_thread(thread_id)`，**删除当前 thread，保留 id**。

触发 reset 的路径：

- 用户输入 `/reset`
- `run_turn` 抛异常
- `run_turn` 被 Ctrl+C 中断

失败后继续复用 thread 会恢复未完成节点，可能重复执行 shell，所以这里必须 reset。

## HITL 审批链路

```text
模型 tool_call
  |
  v
interrupt_on
  |-- write_file / edit_file / delete：总是中断
  |-- execute：policy.needs_approval(command) 为真才中断
  |
  v
LangGraph __interrupt__
  |
  v
run_turn() 收集 pending
  |
  v
resume_command()
  |-- 单个 interrupt：Command(resume={"decisions": [...]})
  |-- 多个 interrupt：{interrupt.id: {"decisions": [...]}}
  |
  v
ask_approval()
  |-- 显示 name / description / args
  |-- TTY：y/N
  |-- 非 TTY：reject
  |
  v
继续 stream
```

关键函数：

- `ask_approval(interrupt, progress)`：把 action requests 逐个展示，返回 decisions。
- `resume_command(interrupts, progress)`：构造 LangGraph `Command`。
- `run_turn(...)`：循环 stream -> 收集 interrupt -> resume，直到没有 pending。

注意：approve 只代表「用户允许这个动作」，不代表「绕过 hard deny」。命令仍会走 `PolicyShellBackend.execute()`。

## 策略链路

```text
Policy.evaluate_command(command)
  |
  +-- 空命令 -> DENY
  +-- hard deny -> DENY
  +-- yolo -> ALLOW
  +-- allow-list=all 且非 read-only -> ALLOW
  +-- safe -> ALLOW
  +-- network / mutating / unknown
        +-- read-only -> DENY
        +-- ask -> ASK
```

`Policy.needs_approval(command)` 只在 `ask` 且判定为 `ASK` 时为真。

`PolicyShellBackend`：

```python
decision = self._policy.evaluate_command(command)
if decision.action == DecisionAction.DENY:
    return ExecuteResponse(
        output=f"Blocked by permission policy: {decision.reason}",
        exit_code=126,
        truncated=False,
    )
return super().execute(command, timeout=timeout)
```

文件工具在 read-only 下直接返回 `WriteResult` / `EditResult` / `DeleteResult` 的 error。

## 文件地图

| 文件 | 职责 | 关键符号 |
| --- | --- | --- |
| `src/minicode/cli.py` | 参数、环境加载、输出、REPL、审批、错误处理 | `main`、`build_parser`、`load_env`、`run_turn`、`ask_approval`、`interactive_loop` |
| `src/minicode/agent.py` | 模型/root/checkpointer/prompt、构建 agent | `DEFAULT_MODEL`、`DEFAULT_CHECKPOINT_DB`、`SHELL_ENV_ALLOWLIST`、`build_agent`、`resolve_db_path` |
| `src/minicode/policy.py` | 权限模式、命令分类、hard deny | `PermissionMode`、`DecisionAction`、`Policy`、`_is_hard_denied` |
| `src/minicode/backends.py` | backend 层拦截 | `PolicyShellBackend` |
| `src/minicode/evals/cli.py` | `minicode eval` 参数/退出码 | `build_parser`、`main` |
| `src/minicode/evals/runner.py` | suite/task 加载、子进程、验证、报告 | `load_suite`、`run_task`、`run_verify`、`run_suite` |
| `src/minicode/evals/worker.py` | 单个 full/bare 任务 | `run_full`、`run_bare`、`main` |
| `tests/test_policy.py` | 策略分类和绕过 | safe、network、mutating、hard deny |
| `tests/test_hitl.py` | 真实 interrupt/resume | write、execute、reject、read-only、yolo |
| `tests/test_cli.py` | CLI 行为和审批提示 | parser、load_env、output、REPL |
| `tests/test_agent.py` | agent 构建 | model、root、db、HITL 配置、checkpointer |
| `tests/test_sqlite.py` | SQLite 跨 agent 持久化 | thread、db |
| `tests/test_evals*.py` | 评测 runner/CLI/worker | suite、pricing、usage、exit code |
| `tests/test_live.py` | 真实模型测试 | live marker、tool use |

## `agent.py` 详解

### 常量

- `DEFAULT_MODEL = "deepseek:deepseek-flash"`
- `DEFAULT_CHECKPOINT_DB = Path(".minicode") / "checkpoints.sqlite"`
- `SHELL_ENV_ALLOWLIST`：允许传给 shell 的环境变量
- `SYSTEM_PROMPT`：虚拟路径、shell 类型、行为约束

### `resolve_model(model)`

优先级：

```text
显式参数 > MINICODE_MODEL > DEFAULT_MODEL
```

空字符串和纯空白会回退。

### `resolve_root(root)`

- `expanduser().resolve()`
- 必须是已存在目录
- 否则抛 `ValueError("workspace root is not a directory: ...")`

这个校验必须在 `build_agent` 内保留。调用方直接传 `Path` 也不能跳过。

### `shell_env()`

只保留 allowlist 中的环境变量。`inherit_env=False`。

结果：

- `PATH`、Windows 系统变量、Python/uv 变量可用；
- `DEEPSEEK_API_KEY` 等 provider key 不可用。

### `resolve_db_path(root, db_path)`

- `db_path` 为空 -> `<root>/.minicode/checkpoints.sqlite`
- 相对路径 -> 相对 root
- 绝对路径 -> 原样使用
- `:memory:` -> 抛 `ValueError`（SQLite 文件模式不支持）

### `build_checkpointer` / `close_checkpointer`

- `build_checkpointer()`：`sqlite3.connect(..., check_same_thread=False)` + `SqliteSaver`。
- `close_checkpointer()`：从 agent 上取 `checkpointer.conn`，关闭连接；没有 `conn`（如 `InMemorySaver`）就跳过。

### `build_agent(...)`

```python
build_agent(
    model=None,
    root=None,
    debug=False,
    checkpoint=False,
    db_path=None,
    permission_mode="ask",
    shell_allow_list=None,
)
```

职责：

1. 解析 root 和 model；
2. 解析 permission mode，创建 `Policy`；
3. 创建 `PolicyShellBackend`；
4. `ask` 模式设置 `interrupt_on`：
   - 文件工具总是中断；
   - `execute` 用 `policy.needs_approval()` 决定是否中断；
5. 选择 checkpointer：
   - `checkpoint=True` -> `SqliteSaver`；
   - 否则 `ask` -> `InMemorySaver`；
   - 否则 `None`；
6. 调 `create_deep_agent(...)`；
7. 创建失败时关闭 SQLite 连接。

`build_agent` 的 `model` 参数可以接收字符串，也可以接收测试注入的 `BaseChatModel`。生产路径优先传字符串，保留 provider profile。

## `policy.py` 详解

### 枚举和结果

```python
class PermissionMode(str, Enum):
    READ_ONLY = "read-only"
    ASK = "ask"
    YOLO = "yolo"


class DecisionAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
```

`Decision` 是 `frozen dataclass`，包含 `action` 和 `reason`。

### 命令分类列表

- `SAFE_COMMAND_PREFIXES`：`ls`、`cat`、`grep`、`git status` 等。
- `NETWORK_COMMANDS` / `NETWORK_PREFIXES`：`curl`、`ssh`、`pip install`、`git push` 等。
- `MUTATING_COMMANDS` / `MUTATING_PREFIXES`：`rm`、`mv`、`python`、`git commit` 等。
- `_SAFE_ARG_DENY`：`--pre`、`--output`、`--ext-diff`、`-exec`、`-delete`。

### 引号感知

- `_split_segments()`：按 `; & |` 和换行切分，但不切引号内部。
- `_syntax_view()`：把引号内的字面量替换成空格；双引号内的 `$` / 反引号保留，因为它们仍可能展开。
- `_tokens()`：用 `shlex.split`，失败时退回简单 split。

### hard deny

`_is_hard_denied()`：

1. 用 `_syntax_view()` 检查 `| sh`、fork bomb 等原始模式；
2. 用 `_split_segments()` 切段；
3. `_segment_hard_denied()` 剥离 `sudo`、`env`、`command`、`nohup`、`exec`、`time` 前缀；
4. shell `-c` 内容递归检查；
5. 覆盖 `rm`、`del`、`rd`、`git push --force`、`mkfs`、`dd of=/dev/*`、`shutdown` 等。

### `_is_safe`

顺序：

1. `_syntax_view()` 后检查重定向和 shell 元字符；
2. 切 segment；
3. 拒绝危险参数；
4. 每个 segment 都要匹配 allow-list 前缀。

注意 `_matches_prefix()` 要求「完全相等」或「前缀 + 空格」，不是裸 `startswith`。

### `_is_network` / `_is_mutating`

先看 `_syntax_view()` 里的 URL 和重定向，再按 segment 的首 token / 前缀分类。

## `backends.py` 详解

`PolicyShellBackend` 只做三件事：

1. `execute()`：policy DENY -> 返回 exit code 126；否则调用 `LocalShellBackend.execute()`。
2. `write()` / `edit()` / `delete()`：`read-only` 下返回 error；否则调用父类。
3. `ask` 的审批不在这里，在 `agent.py` 的 `interrupt_on` + `cli.py` 的 resume。

这个分层很重要：backend 是最后兜底，不是审批 UI。

## `cli.py` 详解

### `load_env()`

- `find_dotenv(usecwd=True)`：从当前工作目录向上找 `.env`
- 只应用 `ENV_ALLOWLIST`
- `os.environ.setdefault`：shell 中已有变量优先
- 忽略空值和纯空白值
- 返回值是实际加载的 `.env` 路径，`--debug` 下会打印

### `message_text(message)`

兼容：

- 字符串 content
- content block 列表
- 普通 dict message

提取 `text`，用于最终回答和工具结果摘要。

### `reasoning_text(message)`

从以下位置提取：

- `content_blocks` 中 `type == "reasoning"` 的 `reasoning` 或 `summary`
- `type == "non_standard"` 且 value 是 thinking/reasoning
- `additional_kwargs.reasoning_content`

多个 block 用换行拼接。

### `print_update(update, console, show_thinking=True)`

消费一个 `stream_mode="updates"` 的 chunk：

- AI message 有 reasoning 且允许显示 -> dim `thinking`
- AI message 有 tool_calls -> `-> tool {args}`
- tool message -> `<- tool result`（截断 200 字符）
- 无 tool_calls 的 AI message -> 记录为 last AI message

返回最后一个 AI message。

### `print_final(message, output)`

- `output.is_terminal` -> Rich `Markdown`
- 非 TTY -> `output.print(text, markup=False, highlight=False, soft_wrap=True)`

非 TTY 必须保持模型原文，否则 `> notes.md` / `| grep` 会拿到渲染后的文本。

### `ask_approval(interrupt, progress)`

- 从 `interrupt.value["action_requests"]` 取动作；
- 显示 name、description、args；
- 非 TTY 直接 reject，并提示重新运行方式；
- TTY 下等待 `y/N`；
- 返回 `[{"type": "approve"}]` 或 `[{"type": "reject", "message": ...}]`。

注意：当前 `dev` 的审批提示直接显示 args；PR #16 会加 secret 脱敏，但尚未合并。

### `resume_command(interrupts, progress)`

- 单个 interrupt：`Command(resume={"decisions": ask_approval(...)})`
- 多个 interrupt：`Command(resume={interrupt.id: {"decisions": ...}})`

### `run_turn(agent, prompt, progress, config, show_thinking=True)`

- `agent.stream({"messages": [...]}, config=config, stream_mode="updates")`
- 每个 update 调 `print_update`
- 遇到 `__interrupt__` 收集起来
- 有 pending -> `resume_command` -> 继续 stream
- 返回最后 AI message

### `interactive_loop(...)`

- 打印交互提示
- `output.input()` 读取一行
- 处理 `/help`、`/reset`、`/exit`、`/quit`
- 每轮调用 `run_turn`
- 异常/Ctrl+C 时 reset thread 并继续

### `main()`

编排入口。注意：

- `checkpoint=not bool(prompt)`：REPL 才启用 SQLite；
- `--interactive` 和 prompt 互斥；
- 非 TTY 无 prompt 时从 stdin 读一次；
- `--db` / `--thread` 只允许 REPL；
- 最终异常由 `print_error` 处理，`--debug` 下直接抛出；
- `finally` 中关闭 checkpointer。

## `evals/` 详解

### `evals/cli.py`

- `minicode eval` 的子命令；
- `--suite` 默认 `smoke`；
- `--baseline full|bare|all`；
- `--task` 可重复；
- `--json` 写报告；
- `--keep` 保留临时 workspace；
- 退出码：`full` 失败返回 1；`all` 以非 bare 结果为准；`bare` 单独跑总是 0。

### `evals/runner.py`

关键函数：

- `load_task()`：读 `task.toml`，解析 prompt、timeout、hidden tests、verify 方式。
- `load_suite()`：读 `evals/suites/<name>.toml`，加载任务。
- `run_task()`：复制 fixture -> 跑 worker -> 跑 verify -> 汇总结果。
- `run_worker()`：启动 `python -m minicode.evals.worker` 子进程。
- `run_verify()`：hidden tests 或 `verify_command` / `verify.py`。
- `run_suite()`：遍历 baseline/task，临时目录，最后清理或保留。
- `print_report()`：Rich 表格 + 每个 baseline 的汇总。

验证隔离：

- `worker_env()`：包含 provider key（agent 要调用模型）。
- `verification_env()`：`shell_env()` + `PYTHONPATH=workspace`，不含 provider key。
- hidden tests 复制到 workspace 同级目录，不进入 agent 可见的 workspace。
- pytest 使用 `evals/pytest-safe.ini`，`--confcutdir` 限制配置，先 `--collect-only` 确认收集到测试。

### `evals/worker.py`

- `run_full()`：`build_agent(permission_mode="yolo", checkpoint=False)`，流式收集 final、tool_calls、usage，超过 max_tool_calls 抛错。
- `run_bare()`：`init_chat_model(model).invoke(prompt)`，没有工具。
- `main()`：读 prompt 文件，跑对应 baseline，写 JSON 结果（成功或失败都写）。

## 测试导读

### `tests/test_policy.py`

覆盖：

- read-only 的 safe / unsafe 命令
- hard deny 在所有模式生效
- ask 模式对网络/变更/未知命令返回 ASK
- shell 元字符、危险参数、引号字面量
- `rm` 灾难性变体、`$HOME`、wrapper
- allow-list、`all`、read-only 忽略 `all`
- `needs_approval`、非法模式

### `tests/test_hitl.py`

覆盖：

- `write_file` 触发 interrupt，approve 后写入
- reject 后不落盘
- `execute` 触发 interrupt，approve 后执行
- read-only 不触发 interrupt，直接拒绝写入
- yolo 不触发 interrupt，直接写入
- `run_turn` 真实 stream interrupt + resume

### `tests/test_cli.py`

覆盖：

- `message_text`、`reasoning_text`、`short_json`
- `print_update` 的工具/思考输出
- `print_final` TTY / 非 TTY
- `load_env` 的 CWD、父目录、allowlist、shell 优先、空值、空白
- 参数解析
- 审批：approve、reject、非 TTY
- REPL：正常轮次、`/reset`、失败 reset、EOF
- `main`：参数冲突、SQLite 选项限制

### `tests/test_agent.py`

覆盖：

- model 优先级和空值回退
- root 不存在时抛错
- checkpointer 可选；ask 用 InMemorySaver
- read-only / yolo 不启用 HITL
- ask 的 `interrupt_on` 配置和 `when`
- 创建失败时关闭 SQLite
- db 路径解析
- shell env 不含 API key
- shell hint 与平台匹配

### `tests/test_sqlite.py`

覆盖：

- 两个 agent 使用同一个 SQLite db 和 thread
- 第二个 agent 能看到第一个 agent 的消息

### `tests/test_evals*.py`

覆盖：

- smoke suite 有 20 个任务
- 验证环境不含 secret
- 相对 evals dir 解析
- pricing / cached token 成本
- suite 汇总
- CLI 参数、退出码、JSON 输出、keep
- worker 的 usage、tool limit、full/bare、失败记录

### `tests/test_live.py`

真实模型测试，`pytest -m live` 手动跑：

- 简单回复
- 使用 `ls` 工具

## 如何扩展

### 加一个 safe 命令

1. 在 `SAFE_COMMAND_PREFIXES` 加前缀（或让用户在 `--shell-allow-list` 加）。
2. 在 `tests/test_policy.py` 加：
   - safe 下允许；
   - 带危险参数时拒绝；
   - 带 shell 元字符时拒绝。
3. 确认 read-only 和 ask 的行为都符合预期。

### 加一个 hard deny 规则

1. 在 `_segment_hard_denied()` 或 `_RAW_DENY_PATTERNS` 加规则。
2. 最好先剥离 wrapper（`sudo`、`env`、`shell -c`）。
3. 加两类测试：
   - 所有模式都 DENY；
   - 普通文本/正常命令不误伤。

### 加一个 CLI 参数

1. `build_parser()` 加参数。
2. `main()` 把参数传到 `build_agent` / `run_turn` / `interactive_loop`。
3. 加 parser 测试和 `main` 透传测试。
4. 如果参数影响安全边界，写进 README / AGENTS。

### 加一个 eval 任务

1. 创建 `evals/tasks/<id>/fixture/`。
2. 写 `prompt.md`、`task.toml`。
3. 验证方式二选一：
   - `hidden/test_hidden.py`；
   - `verify.py` 或 `verify_command`。
4. 加入 `evals/suites/smoke.toml`。
5. 先跑 `uv run minicode eval --task <id>`，再跑 smoke。

### 换模型/provider

```bash
uv add langchain-openai
uv run minicode --model openai:gpt-5.5 "review this change"
```

或设置：

```dotenv
MINICODE_MODEL=openai:gpt-5.5
```

不要为了「统一」把模型字符串换成 `init_chat_model()` 实例，除非接受 provider profile 行为变化。

## 常见坑

1. **文件工具路径**：用 `/src/...`，不要用 `C:\...`。
2. **shell 路径**：用相对路径，工作目录已经是 workspace 根。
3. **provider key**：不要指望 shell 子进程能读到；它被 allowlist 过滤。
4. **`.env`**：不要加 base URL/endpoint 类变量；会被忽略。
5. **非 TTY**：最终回答必须是原文，不要渲染 Markdown。
6. **checkpointer**：单次 ask 有 InMemorySaver；REPL 才有 SQLite。
7. **REPL 失败**：必须 reset thread，不要恢复未完成节点。
8. **审批**：approve 不等于绕过 hard deny。
9. **`--debug`**：会打印更多信息并重新抛出异常，不是生产模式。
10. **评测**：hidden tests 不要放进 agent 的 workspace；验证环境不要带 provider key。

## 调试命令

```bash
uv run minicode --help
uv run minicode --debug "explain this repo"
uv run minicode -i
uv run pytest -q
uv run pytest -q tests/test_policy.py -k hard_deny
uv run pytest -q tests/test_hitl.py
uv run pytest -q --cov=minicode --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m compileall -q src
```
