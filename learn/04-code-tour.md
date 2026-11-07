# 代码导读

## 推荐阅读顺序

```text
pyproject.toml
  -> src/minicode/__init__.py
  -> src/minicode/__main__.py
  -> src/minicode/cli.py（先看 main）
  -> src/minicode/agent.py
  -> tests/test_cli.py
  -> tests/test_agent.py
```

先看入口，再看 agent 构建，最后看测试如何锁住行为。

### 读 `cli.py` 时不要按行号顺序

文件里的定义顺序是：

```text
load_env
message_text
short_json
print_update
print_final
print_error
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
  -> interactive_loop
       -> run_turn
  -> print_final / print_error
```

助手函数放在 `main` 前面只是 Python 文件的常见组织方式，不代表它们是入口。**先读 `main`，再顺着它调用的函数往下读，理解成本会低很多。**

## 为什么 `print_update` 长这样

它消费的是 LangGraph `stream_mode="updates"` 的一个 chunk，形状大致是：

```python
{
    "node_name": {
        "messages": [AIMessage(...), ToolMessage(...)],
    },
    ...
}
```

所以它做了三件事：

1. 防御性检查 `update` 是否是 dict
2. 遍历每个 node update 里的 `messages`
3. 把 AI 的 tool call 和 Tool 的结果打到 stderr，并返回最后一个 AI message

其中 `update: Any` 是刻意的：node 名字和 payload 由 LangGraph / Deep Agents 决定，写成精确类型反而会骗人。运行时的 `isinstance` 检查才是真实的类型边界。

这个函数确实有一个小设计味道：**既负责打印，又负责返回 final message**。当前规模下可以接受；如果以后逻辑继续变复杂，建议拆成：

```python
def render_update(update, console) -> None: ...
def last_ai_message(update) -> Any: ...
```

让 I/O 和“取最后一个回答”各自独立。现在不拆也没问题，读的时候把它理解成 “render + return last AI” 即可。


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
  |-- build_agent(checkpoint=False)
  |-- run_turn()
  |     |-- agent.stream(..., stream_mode="updates")
  |     |-- print_update() -> stderr
  |     `-- 返回最后一个 AI message
  |-- print_final() -> stdout
  `-- return 0 / 1
```

### `main()` 的关键分支

1. `prompt and args.interactive` -> 参数错误
2. 无 prompt、非交互、非 TTY -> 从 stdin 读 prompt
3. 仍然没有 prompt -> 参数错误
4. 有 prompt -> 单次任务
5. 无 prompt -> `interactive_loop()`

`--debug` 只影响：

- 是否打印 env 路径、workspace、model
- 异常是否直接抛出完整 traceback

## 一次 REPL 执行

```text
main()
  |-- build_agent(checkpoint=True)
  |-- config = make_config()          # thread_id = minicode-<uuid>
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
              `-- print_final() -> stdout
```

### thread 生命周期

- `make_config()`：生成初始 `thread_id`
- `reset_thread(config, agent)`：
  1. 记录旧 thread
  2. 生成新 thread
  3. 如果 agent 有 `checkpointer`，调用 `delete_thread(old)`

触发 reset 的路径：

- 用户输入 `/reset`
- `run_turn` 抛异常
- `run_turn` 被 Ctrl+C 中断

失败后继续复用 thread 会恢复未完成节点，可能重复执行 shell，所以这里必须 reset。

## 文件地图

| 文件 | 职责 | 关键符号 |
| --- | --- | --- |
| `src/minicode/cli.py` | 参数解析、环境加载、输出、REPL、错误处理 | `main`、`build_parser`、`load_env`、`run_turn`、`interactive_loop`、`print_final`、`print_update` |
| `src/minicode/agent.py` | 模型/root 解析、环境过滤、prompt、构建 agent | `DEFAULT_MODEL`、`SHELL_ENV_ALLOWLIST`、`SYSTEM_PROMPT`、`resolve_model`、`resolve_root`、`shell_env`、`shell_hint`、`build_agent` |
| `src/minicode/__main__.py` | `python -m minicode` 入口 | `SystemExit(main())` |
| `tests/test_cli.py` | CLI 行为测试 | 输出、REPL、参数、错误路径 |
| `tests/test_agent.py` | agent 构建测试 | 模型解析、root 校验、shell env、checkpointer |

## `agent.py` 详解

### 常量

- `DEFAULT_MODEL = "deepseek:deepseek-chat"`
- `SHELL_ENV_ALLOWLIST`：允许传给 shell 的环境变量
- `SYSTEM_PROMPT`：虚拟路径、shell 类型、行为约束

### `resolve_model(model)`

优先级：

```text
显式参数 > MINICODE_MODEL > DEFAULT_MODEL
```

空字符串会回退到环境变量/默认值。

### `resolve_root(root)`

- `expanduser().resolve()`
- 必须是已存在目录
- 否则抛 `ValueError("workspace root is not a directory: ...")`

这个校验必须在 `build_agent` 内保留。调用方直接传 `Path` 也不能跳过。

### `shell_env()`

只保留 allowlist 中的环境变量。`inherit_env=False`。

结果：

- `PATH`、Windows 系统变量、Python/uv 变量可用
- `DEEPSEEK_API_KEY` 等 provider key 不可用

### `shell_hint()`

按平台生成 prompt 片段：

- Windows：`cmd.exe`、`%VAR%`
- 其他：POSIX sh、`$VAR`

### `build_agent(...)`

```python
build_agent(
    model=None,
    root=None,
    debug=False,
    checkpoint=False,
)
```

职责：

1. 解析 root 和 model
2. 创建 `LocalShellBackend(root_dir=root, env=shell_env(), inherit_env=False)`
3. 调用 `create_deep_agent(...)`
4. `checkpoint=True` 时挂 `MemorySaver()`

默认 `checkpoint=False`，所以直接调用 `build_agent()` 后 `invoke()` / `stream()` 不需要 `thread_id`。

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

### `print_update(update, console)`

消费一个 `stream_mode="updates"` 的 chunk：

- `tool_calls` -> 青色 `-> tool {args}`
- `type == "tool"` -> 绿色 `<- tool result`
- `type == "ai"` 且无 tool calls -> 记录为 last AI message

返回最后一个 AI message。

### `print_final(message, output)`

- `output.is_terminal` -> Rich `Markdown`
- 非 TTY -> `output.print(text, markup=False, highlight=False, soft_wrap=True)`

非 TTY 必须保持模型原文，否则 `> notes.md` / `| grep` 会拿到渲染后的文本。

### `run_turn(agent, prompt, progress, config)`

- `agent.stream({"messages": [...]}, config=config, stream_mode="updates")`
- 每个 update 调 `print_update`
- 返回最后 AI message

### `interactive_loop(...)`

- 打印交互提示
- `output.input()` 读取一行
- 处理 `/help`、`/reset`、`/exit`、`/quit`
- 每轮调用 `run_turn`
- 异常/Ctrl+C 时 reset thread 并继续

### `main()`

编排入口。注意：

- `checkpoint=not bool(prompt)`：REPL 才启用
- `--interactive` 和 prompt 互斥
- 非 TTY 无 prompt 时从 stdin 读一次
- 最终异常由 `print_error` 处理，`--debug` 下直接抛出

## 测试导读

### `tests/test_agent.py`

覆盖：

- model 优先级和空字符串回退
- root 不存在时 `build_agent` 抛错
- checkpointer 默认关闭、显式开启
- shell env 不含 API key
- shell hint 与平台匹配

### `tests/test_cli.py`

覆盖：

- `message_text`、`short_json`
- `print_update` 工具调用/结果
- `print_final` TTY / 非 TTY
- `load_env` 的 CWD、父目录、allowlist、shell 优先、空值、空白
- 参数解析
- REPL：正常轮次、`/reset`、失败 reset、EOF
- `main`：`-i` + prompt 冲突、非 TTY 无 prompt

运行：

```bash
uv run pytest -q
```

## 如何扩展

### 加一个自定义工具

在 `build_agent` 里给 `create_deep_agent` 传 `tools=[...]`：

```python
from langchain.tools import tool

@tool
def count_lines(path: str) -> int:
    """Count lines in a workspace file."""
    ...
```

注意工具参数应使用虚拟路径，除非它明确只接受 shell 路径。

### 换模型/provider

```bash
uv add langchain-openai
uv run minicode --model openai:gpt-5.5 "review this change"
```

或设置：

```dotenv
MINICODE_MODEL=openai:gpt-5.5
```

不要为了“统一”把模型字符串换成 `init_chat_model()` 实例，除非接受 provider profile 行为变化。

### 加 HITL

需要：

1. `build_agent(..., interrupt_on={"execute": True})`
2. checkpointer
3. CLI 处理 `__interrupt__` 并 resume

只改 prompt 写“请先询问”不算实现。

### 加静态命令策略

如果要加，建议：

- 纯函数分类器
- 在 backend 层拦截
- 返回明确 tool error
- 明确文档：这是策略层，不是沙箱
- 单独测试误报/漏报

`tmp` 分支有这类实验，可参考，但不要把它当作已合并能力。

## 常见坑

1. **文件工具路径**：用 `/src/...`，不要用 `C:\...`。
2. **shell 路径**：用相对路径，工作目录已经是 workspace 根。
3. **provider key**：不要指望 shell 子进程能读到；它被 allowlist 过滤。
4. **`.env`**：不要加 base URL/endpoint 类变量；会被忽略。
5. **非 TTY**：最终回答必须是原文，不要渲染 Markdown。
6. **checkpointer**：默认关闭；只有 REPL 需要 `thread_id`。
7. **REPL 失败**：必须 reset thread，不要恢复未完成节点。
8. **`--debug`**：会打印更多信息并重新抛出异常，不是生产模式。

## 调试命令

```bash
uv run minicode --help
uv run minicode --debug "explain this repo"
uv run minicode -i
uv run pytest -q
uv run python -m compileall -q src
uv build
```
