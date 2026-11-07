# 心智模型

## 一张图

```text
用户
  |
  | prompt / REPL 输入
  v
cli.py
  |-- load_env()            只读 .env 中的安全配置
  |-- build_parser()        解析 --model / --root / --debug / -i
  |
  v
agent.py: build_agent()
  |-- resolve_root()        workspace 必须是已存在目录
  |-- resolve_model()       CLI > MINICODE_MODEL > deepseek:deepseek-chat
  |-- shell_env()           过滤环境变量，不把 provider key 给 shell
  |-- SYSTEM_PROMPT         虚拟路径 + shell 类型 + 行为约束
  |-- LocalShellBackend     root_dir = workspace
  |
  v
Deep Agents graph（LangGraph）
  |-- 规划 / todo
  |-- 文件工具：ls / read_file / write_file / edit_file / glob / grep
  |-- execute：调用 LocalShellBackend
  |-- task：子 agent
  |-- summarization：长上下文压缩
  |
  v
stream_mode="updates"
  |
  +--> print_update()       向 stderr 打工具调用和结果摘要
  |
  v
最后一个 AI message
  |
  +--> print_final()        stdout：TTY 下 Markdown，管道下原文
```

## 两条运行路径

### 1. 单次任务

```text
main()
  -> build_agent(checkpoint=False)
  -> run_turn(prompt)
  -> agent.stream(...)
  -> print_final()
  -> exit 0/1
```

单次任务不创建 checkpointer，也不需要 `thread_id`。跑完就结束。

### 2. REPL

```text
main()
  -> build_agent(checkpoint=True)
  -> interactive_loop()
       -> output.input("minicode> ")
       -> run_turn(prompt)
       -> print_final()
       -> 下一轮
```

REPL 使用同一个 `config["configurable"]["thread_id"]`，所以后续轮次能看到前面的消息。

`/reset`、单轮异常、Ctrl+C 会：

1. 删除旧 thread 的 checkpoint
2. 生成新的 `thread_id`
3. 下一轮从空上下文开始

这样不会把上一轮未完成的图节点带到下一轮。

## 状态模型

要区分两种“状态”：

| 状态 | 存在哪里 | 生命周期 |
| --- | --- | --- |
| 对话消息、规划、子 agent 状态 | LangGraph graph state / `MemorySaver` | REPL 进程内 |
| workspace 文件 | 真实磁盘，通过 `LocalShellBackend` 访问 | 持久 |
| shell 进程环境 | 每次 `execute` 子进程 | 单次命令 |
| `.env` 配置 | 进程环境变量 | 进程内 |

`MemorySaver` 只保存 graph state，不保存文件。文件改动是真实的、持久的。

## 工具模型

Deep Agents 默认提供：

- 文件：`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`
- 执行：`execute`
- 委派：`task`

MiniCode 没有自己重写这些工具，而是：

- 用 `LocalShellBackend` 决定文件根目录和 shell 行为
- 用 `SYSTEM_PROMPT` 告诉模型路径语义和行为边界

### 路径语义

文件工具使用**虚拟文件系统**：

```text
/                     -> workspace 根
/src/minicode/cli.py  -> <workspace>/src/minicode/cli.py
```

不要给文件工具传 `C:\...`。Windows 盘符路径会被拒绝。

Shell 命令不同：它在 workspace 根目录下启动，使用相对路径，Windows 下是 `cmd.exe`。

## Prompt 的三层来源

最终 system prompt 大致由三部分组成：

1. 调用方传入的 `SYSTEM_PROMPT`
2. Deep Agents / harness profile 的 base prompt
3. profile 的 suffix（如果模型/provider 有）

MiniCode 只控制第一层。`SYSTEM_PROMPT` 负责：

- 虚拟路径规则
- shell 类型（cmd.exe 或 POSIX sh）
- 读文件、聚焦修改、运行验证
- 破坏性命令要谨慎
- 完成后总结

## 环境变量

有两条独立的 allowlist，不要混淆：

### `.env` 加载 allowlist

`cli.load_env()` 只应用：

- `MINICODE_MODEL`
- 已知 provider API key

它会忽略 `OPENAI_BASE_URL`、`*_API_BASE`、endpoint 类变量，避免陌生仓库的 `.env` 把 key 重定向到其他地址。

### shell 继承 allowlist

`agent.shell_env()` 只把 PATH、Windows 系统变量、Python/uv 相关变量传给 `execute` 子进程。

因此：

- shell 能运行 `uv`、`git`、`python` 等命令
- shell 里拿不到 `DEEPSEEK_API_KEY` 等 provider key

## 输出模型

| 通道 | 内容 | 目的 |
| --- | --- | --- |
| stdout | 最终回答 | 可被管道/重定向消费 |
| stderr | `-> tool`、`<- tool`、错误、进度 | 不污染最终文本 |
| TTY stdout | Rich Markdown | 人类阅读 |
| 非 TTY stdout | 原始文本 | `> notes.md`、`| grep` 保持模型原文 |

`print_final()` 是这条边界的唯一实现点。

## 失败模型

- 缺 API key：`print_error()` 输出一行明确提示，退出码 1。
- `--root` 不存在：`resolve_root()` 抛 `ValueError`，CLI 捕获并输出。
- 单轮异常：单次任务返回 1；REPL 打印错误、重置 thread、继续下一轮。
- Ctrl+C：单次任务返回 130；REPL 重置 thread、继续。
- `--debug`：不吞异常，直接抛出完整 traceback。

## 安全边界

当前实现的实际边界是：

1. workspace 根目录限制文件工具的虚拟路径
2. shell 环境变量过滤
3. system prompt 的行为约束

它**没有**：

1. 文件/网络/进程沙箱
2. HITL 审批
3. 静态命令拦截
4. 操作系统级权限隔离

所以正确的心智模型是：**一个受提示词和路径约定约束的本地开发助手，不是一个安全执行环境。**

## 记住这几条

- `cli.py` 负责“怎么运行”，`agent.py` 负责“运行什么”。
- 单次任务无 checkpointer，REPL 才有。
- 文件路径是虚拟的，shell 路径是相对的。
- stdout 只放最终回答，stderr 放过程。
- `.env` 有 allowlist，shell env 也有 allowlist。
- 没有 HITL；破坏性命令不会等你确认。
