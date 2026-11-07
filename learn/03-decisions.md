# 关键决策

本文记录 MiniCode 当前形态背后的取舍。目标不是复述代码，而是说明：**为什么这样做、代价是什么、以后不要轻易破坏什么。**

## 决策速览

| # | 决策 | 主要收益 | 主要代价 |
| --- | --- | --- | --- |
| 1 | 用 Deep Agents，而不是从零写 agent loop | 规划、文件工具、子 agent、压缩都现成 | 依赖框架行为和版本 |
| 2 | 用 `LocalShellBackend` | 真正能读文件、跑命令 | 没有隔离，权限等于当前用户 |
| 3 | `create_deep_agent` 接收 model 字符串 | 保留 provider profile | 依赖 provider 包和 key |
| 4 | 默认 `deepseek:deepseek-chat` | 便宜、够用、易测试 | 用户需要 DeepSeek key |
| 5 | `.env` 只加载安全 key | 防止陌生仓库重定向端点 | Azure endpoint 需在 shell 设置 |
| 6 | shell 环境变量 allowlist | 不把 provider key 暴露给命令 | 某些命令需要手动加变量 |
| 7 | REPL 才启用 checkpointer | 单次调用契约简单 | 两套运行路径 |
| 8 | REPL 失败后轮换 thread | 避免恢复未完成节点 | 失败会丢失上下文 |
| 9 | Rich 进度 + 原文管道输出 | 人类可读，脚本可消费 | 需要区分 TTY |
| 10 | 没有 HITL / 静态 guard | 实现简单、行为直接 | 安全责任在用户 |

## 1. 选择 Deep Agents

**决策**：用 `deepagents.create_deep_agent` 作为 harness，而不是自己实现 tool loop。

**原因**：

- 文件工具、`execute`、子 agent、todo、上下文压缩已经是成熟实现。
- MiniCode 的重点是“如何配置和约束一个 coding agent”，不是重写 agent runtime。
- LangGraph 的 stream/checkpoint 直接可用。

**代价**：

- 行为会随 `deepagents` 版本变化。
- system prompt 实际由 MiniCode 的 prompt + harness profile 共同组成，不能假设只有自己那段。
- 模型必须支持 tool calling。

**不要回归**：不要为了“自己掌控”随手替换成手写 loop；那会把项目从“薄封装”变成“半个框架”。

## 2. 选择 LocalShellBackend

**决策**：用 `LocalShellBackend`，不用 `StateBackend` 或 sandbox。

**原因**：

- 这是一个本地开发 CLI，需要真实修改当前仓库。
- 文件工具和 shell 都直接作用于 workspace。
- `StateBackend` 只能玩内存文件系统，不能真正改代码。

**代价**：

- 没有沙箱、没有资源限制、没有进程隔离。
- shell 能读取当前用户能读的任何文件。
- 命令副作用是真实且不可逆的。

**不要回归**：文档必须继续明确写“不是沙箱”。如果要做生产/多租户版本，应该换 sandbox backend，而不是在这层加几个正则就宣称安全。

## 3. model 字符串直接传给 create_deep_agent

**决策**：

```python
create_deep_agent(model=model_name, ...)
```

而不是：

```python
create_deep_agent(model=init_chat_model(...), ...)
```

**原因**：

- Deep Agents 收到字符串时会走自己的 `resolve_model()` / provider profile。
- 传 `BaseChatModel` 实例会绕过 profile，丢失 provider 特有配置（例如 OpenAI Responses API、OpenRouter attribution、NVIDIA billing header）。

**代价**：

- provider 初始化错误会在 `create_deep_agent` 内部发生。
- 需要安装对应 provider 集成包，例如 `langchain-deepseek`。

**不要回归**：不要在 `build_agent` 里把字符串换成模型实例，除非明确接受 profile 行为变化。

## 4. 默认 DeepSeek

**决策**：`DEFAULT_MODEL = "deepseek:deepseek-chat"`。

**原因**：

- 成本和可用性适合本地 coding agent。
- 已安装 `langchain-deepseek`，开箱可跑。
- 模型 id 稳定，适合作为默认值。

**代价**：

- 没有 DeepSeek key 时首次运行会失败（CLI 会给出提示）。
- 其他 provider 需要额外安装集成包并用 `--model` / `MINICODE_MODEL` 覆盖。

**不要回归**：默认值可以换，但必须同步 `.env.example`、README、AGENTS.md 和测试里的默认模型断言。

## 5. `.env` 只加载安全 key

**决策**：`load_env()` 用 `find_dotenv(usecwd=True)` 从当前目录向上找 `.env`，但只应用 allowlist 中的变量。

允许：

- `MINICODE_MODEL`
- 已知 provider API key

忽略：

- `OPENAI_BASE_URL`
- `*_API_BASE`
- `AZURE_OPENAI_ENDPOINT`
- 其他 endpoint/base URL 类变量

**原因**：

- MiniCode 经常在“别人的仓库”里运行，陌生 `.env` 不应能重定向 key。
- 只加载 key 和模型选择，已覆盖主要使用场景。

**代价**：

- Azure 的 endpoint/version 需要在 shell 中设置，不能写进 `.env`。
- 自定义 provider 的 base URL 也不能从 `.env` 配。

**不要回归**：不要把 `*_BASE_URL`、`*_API_BASE`、endpoint 类变量加进 allowlist。需要时在 shell 里设置。

## 6. shell 环境变量 allowlist

**决策**：`LocalShellBackend(inherit_env=False, env=shell_env())`。

保留：

- PATH / PATHEXT / Windows 系统变量
- Python / uv 相关变量
- HOME / TEMP / 用户变量

不保留：

- `DEEPSEEK_API_KEY`
- 其他 `*_API_KEY`
- 任意 secret

**原因**：

- 模型生成的 shell 命令不应该能直接读到 provider key。
- 命令输出会回流给模型，key 一旦进入环境就有泄露路径。

**代价**：

- 某些需要环境变量的项目命令会失败。
- 用户需要在命令里显式传入必要变量。

**不要回归**：不要用 `inherit_env=True` 图省事。

## 7. checkpointer 只在 REPL 启用

**决策**：

- 单次任务：`checkpoint=False`
- REPL：`checkpoint=True`

**原因**：

- 单次任务不需要跨轮状态，保持 `invoke()` / `stream()` 契约简单。
- REPL 需要多轮记忆。
- 如果无条件挂 checkpointer，所有调用方都必须传 `thread_id`，会破坏公开入口。

**代价**：

- `build_agent` 多一个参数。
- 两条路径行为不同，需要测试覆盖。

**不要回归**：默认 `checkpoint=False`，不要让单次调用强制依赖 `thread_id`。

## 8. REPL 失败后轮换 thread

**决策**：失败、Ctrl+C、`/reset` 都换一个新 `thread_id`，并删除旧 thread。

**原因**：

- `MemorySaver` 在执行前就写入输入 checkpoint。
- 如果一轮中途抛错，checkpoint 的 `next` 可能指向未完成节点。
- 下一轮如果复用 thread，会先恢复失败节点，可能重复执行 shell 命令。

**代价**：

- 失败会丢失当前会话上下文。
- 用户会看到 “Context reset” 提示。

**不要回归**：失败后不能继续复用旧 thread。宁可丢上下文，也不要重复执行副作用命令。

## 9. Rich 输出分工

**决策**：

- 进度、工具调用、错误：stderr
- 最终回答：stdout
- TTY：Markdown 渲染
- 非 TTY：原始文本

**原因**：

- `minicode "..." > notes.md` 应该得到模型原文，而不是 Rich 渲染后的 Markdown。
- 进度信息不应污染脚本消费的 stdout。
- 交互终端需要可读性。

**代价**：

- 需要区分 `Console.is_terminal`。
- 测试要覆盖 TTY / 非 TTY 两条路径。

**不要回归**：不要在非 TTY 下用 `Markdown` 渲染最终回答。

## 10. 没有 HITL / 静态 guard

**决策**：当前分支不实现 `interrupt_on`，也不实现静态命令拦截。

**原因**：

- 保持最小实现，先把 agent 跑通。
- HITL 需要 checkpointer、审批循环、resume 协议，复杂度高。
- 静态 guard 容易误报/漏报，不适合伪装成安全边界。

**代价**：

- 破坏性命令不会等待确认。
- 安全完全依赖用户选择可信 workspace。
- system prompt 只能“建议谨慎”，不能强制执行。

**不要回归**：

- 不要在文档里声称有审批或沙箱。
- 如果未来加 HITL，必须真正处理 `__interrupt__` 和 resume，而不是只写 prompt。
- 如果未来加静态 guard，要明确它是“提高下限的策略层”，不是安全边界。

## 本分支没有的东西

以下内容出现在 `tmp` 实验分支，但**不在当前 `dev`**：

- `guard.py` 静态命令分类
- `GuardedShellBackend`
- `trace.py` 每轮 JSON trace
- `minicode.evals` model-free harness 检查

学习本目录时不要把那些当成现有实现。

## 开放问题

1. 是否要引入 HITL，真正拦住高风险 shell？
2. 长会话如何裁剪上下文？目前依赖 Deep Agents 的 summarization。
3. Windows 上 `del /s`、PowerShell 删除等路径如何治理？
4. 是否要把 provider 安装做成 extras，而不是默认依赖？
5. 何时补 CI、lint、typecheck？
6. 顶层 LICENSE 和 `pyproject.toml` 的 license 字段仍未定。

## 一句话总结

MiniCode 的设计哲学是：**薄封装、真实 workspace、明确边界、可读可测**。任何改动如果让边界更模糊，或者让“安全”变成文档口号而不是实际机制，都值得停下来重新讨论。
