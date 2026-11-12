# 关键决策

本文记录 MiniCode 当前形态背后的取舍。目标不是复述代码，而是说明：**为什么这样做、代价是什么、以后不要轻易破坏什么。**

## 决策速览

| # | 决策 | 主要收益 | 主要代价 |
| --- | --- | --- | --- |
| 1 | 用 Deep Agents，而不是从零写 agent loop | 规划、文件工具、子 agent、压缩都现成 | 依赖框架行为和版本 |
| 2 | 用 `PolicyShellBackend` 包 `LocalShellBackend` | 真实读写 + 统一策略入口 | 仍然不是沙箱 |
| 3 | 三档权限模式 + ask HITL | 默认更安全，危险动作可审批 | 多一套 interrupt/resume 状态机 |
| 4 | hard deny-list 作为最后兜底 | 连 yolo 也拦灾难命令 | 规则需要维护，可能误报/漏报 |
| 5 | conservative safe allow-list | read-only/ask 下常用读命令直接跑 | 复杂命令会退化成审批/拒绝 |
| 6 | REPL 用 SQLite checkpointer | 会话可跨进程恢复 | 需要管理 db/thread 和并发 |
| 7 | ask 单次任务用 InMemorySaver | 单次也能 interrupt/resume | 单次也有进程内状态 |
| 8 | 失败/`/reset` 删除当前 thread | 避免恢复未完成节点 | 失败会丢失上下文 |
| 9 | `.env` 只加载安全 key | 防止陌生仓库重定向端点 | Azure endpoint 需在 shell 设置 |
| 10 | shell 环境变量 allowlist | 不把 provider key 暴露给命令 | 某些命令需要手动加变量 |
| 11 | model 字符串直接传给 `create_deep_agent` | 保留 provider profile | 依赖 provider 包和 key |
| 12 | Rich 进度 + 原文管道输出 | 人类可读，脚本可消费 | 需要区分 TTY |
| 13 | reasoning 单独走 stderr | 不污染最终回答 | 需要处理多种 reasoning block 形状 |
| 14 | fixture evals + 可执行验证 | 能回答「真的改对了吗」 | 有 API 成本和 fixture 维护成本 |
| 15 | CI 质量门 + 手动 live 流程 | PR 不烧钱，质量有底线 | live 问题不会在 PR 自动暴露 |
| 16 | 提交/审阅身份分离 | 提交可自动化，审阅有明确责任人 | 流程更繁琐 |

## 1. 选择 Deep Agents

**决策**：用 `deepagents.create_deep_agent` 作为 harness，而不是自己实现 tool loop。

**原因**：

- 文件工具、`execute`、子 agent、todo、上下文压缩已经是成熟实现。
- MiniCode 的重点是「如何配置和约束一个 coding agent」，不是重写 agent runtime。
- LangGraph 的 stream/checkpoint/interrupt 直接可用。

**代价**：

- 行为会随 `deepagents` / LangChain 版本变化。
- system prompt 实际由 MiniCode 的 prompt + harness profile 共同组成，不能假设只有自己那段。
- 模型必须支持 tool calling。

**不要回归**：不要为了「自己掌控」随手替换成手写 loop；那会把项目从「薄封装」变成「半个框架」。

## 2. 用 PolicyShellBackend，而不是裸 LocalShellBackend

**决策**：`PolicyShellBackend` 继承 `LocalShellBackend`，在 `execute` / `write` / `edit` / `delete` 上做最后拦截。

**原因**：

- 这是一个本地开发 CLI，需要真实修改当前仓库。
- 文件工具和 shell 都直接作用于 workspace。
- 把 hard deny 和 read-only 文件拒绝放在 backend，能覆盖「调用方绕过 CLI」的路径。

**代价**：

- 没有沙箱、没有资源限制、没有进程隔离。
- shell 能读取当前用户能读的任何文件。
- 命令副作用是真实且不可逆的。

**不要回归**：文档必须继续明确写「不是沙箱」。如果要做生产/多租户版本，应该换 sandbox backend，而不是在这层加几个正则就宣称安全。

## 3. 三档权限模式 + ask HITL

**决策**：

- `read-only`：文件写/删拒绝，shell 只允许 safe 命令。
- `ask`（默认）：文件修改和危险 shell 要审批。
- `yolo`：跳过审批，但 hard deny 仍生效。

**原因**：

- 默认不应该让模型静默执行危险命令。
- 本地开发又需要「常用读命令直接跑」的低摩擦路径。
- `yolo` 是显式选择，适合 eval、CI 或用户明确信任的场景。

**代价**：

- 需要 LangGraph checkpointer 支持 interrupt/resume。
- CLI 要处理 `__interrupt__`、approve/reject、resume。
- 非 TTY 必须 fail closed，否则 CI 会挂起。

**不要回归**：

- 非 TTY 不能等待输入，必须拒绝。
- approve 之后仍要走 backend 的 hard deny。
- 不要把「有审批」写成「有沙箱」。

## 4. hard deny-list 作为最后兜底

**决策**：`Policy` 在所有模式之前先检查 hard deny，`PolicyShellBackend.execute()` 再检查一次。

**覆盖示例**：

- `rm -rf /`、`rm -rf /*`、`rm -rf $HOME`
- `git push --force` / `-f`
- `curl ... | sh`、`wget ... | bash`
- `mkfs*`、`dd of=/dev/*`
- Windows `format C:`、`del /s /q C:\`
- `shutdown`、`reboot`、`fdisk`
- `sudo` / `env` / `command` / `nohup` / shell `-c` 包装后的同类命令

**原因**：

- 这些命令的代价太高，不能只靠用户审批或模型自觉。
- `yolo` 也需要一个最低下限。

**代价**：

- 规则维护成本；命令语法跨平台，容易有漏网之鱼。
- 可能误伤正常文本（例如 commit message 里出现 `shutdown`）；所以判定基于 token/segment，不是裸字符串。

**不要回归**：hard deny 只能作为 guardrail，不能替代 sandbox。新增规则时要同时加「不误伤」和「能拦截」的测试。

## 5. conservative safe allow-list

**决策**：只有「无 shell 元字符 + 安全参数 + 命令前缀匹配」的简单命令才算 safe。

**原因**：

- read-only 和 ask 的默认路径需要低摩擦。
- 但 `$(...)`、反引号、`&`、重定向、`find -delete`、`rg --pre`、`git diff --output` 都可能写文件或执行程序。
- 引号内的普通字面量（如 `git log --pretty='%h (%s)'`）不应该被误判。

**代价**：

- 复杂但只读的命令（例如复杂的 `git log` 管道）会退化成审批/拒绝。
- 需要维护 `_SAFE_ARG_DENY` 和引号感知解析。

**不要回归**：

- 不要把 safe 判定简化成纯字符串前缀。
- 不要先判 safe 再判 mutating/network；safe 必须足够保守。
- 引号内的 `$` / 反引号仍可能展开，不能全部当字面量。

## 6. REPL 用 SQLite checkpointer

**决策**：`checkpoint=True` 时使用 `SqliteSaver`，默认数据库 `<root>/.minicode/checkpoints.sqlite`。

**原因**：

- 会话需要跨进程恢复。
- SQLite 是本地 CLI 最低依赖的选择。
- LangGraph checkpoint 能同时保存消息、计划和中断状态。

**代价**：

- 数据库包含对话和工具输出，不能提交。
- 并行 REPL 需要不同的 `--thread` / `--db`。
- 需要管理连接关闭和 schema。

**不要回归**：

- `.minicode/` 和 `*.sqlite*` 必须继续被 git 忽略。
- `close_checkpointer()` 必须在正常退出和异常路径都执行。
- `:memory:` 不作为 `--db` 值；单次 ask 用 `InMemorySaver`，不需要用户传 db。

## 7. ask 单次任务用 InMemorySaver

**决策**：`build_agent(checkpoint=False, permission_mode="ask")` 仍然创建 `InMemorySaver`。

**原因**：

- LangGraph 的 interrupt/resume 需要 checkpointer。
- 单次任务不写 SQLite，但审批仍要能暂停和恢复。
- 进程退出后状态自然消失，符合单次任务契约。

**代价**：

- 「单次任务没有状态」这句话不准确：它有进程内 graph state。
- 需要测试区分「无 checkpointer」和「无持久化 checkpointer」。

**不要回归**：不要因为单次任务就删掉 ask 的 InMemorySaver，否则审批会坏。

## 8. 失败/`/reset` 删除当前 thread

**决策**：`reset_thread()` 删除当前 thread 的 checkpoint，但保留 thread id。

**原因**：

- 失败或中断时，checkpoint 的 `next` 可能指向未完成节点。
- 复用同一 thread 可能恢复失败节点，重复执行 shell。
- 保留 thread id 让 CLI 参数和日志更稳定。

**代价**：

- 失败会丢失当前会话上下文。
- 用户会看到 “Context reset” 提示。

**不要回归**：失败后不能继续复用旧 thread；宁可丢上下文，也不要重复执行副作用命令。

## 9. `.env` 只加载安全 key

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

- MiniCode 经常在「别人的仓库」里运行，陌生 `.env` 不应能重定向 key。
- 只加载 key 和模型选择，已覆盖主要使用场景。

**代价**：

- Azure 的 endpoint/version 需要在 shell 中设置，不能写进 `.env`。
- 自定义 provider 的 base URL 也不能从 `.env` 配。

**不要回归**：不要把 `*_BASE_URL`、`*_API_BASE`、endpoint 类变量加进 allowlist。`MINICODE_PERMISSION_MODE` / `MINICODE_SHELL_ALLOW_LIST` 也只从 shell 读，不从 `.env` 读。

## 10. shell 环境变量 allowlist

**决策**：`PolicyShellBackend(inherit_env=False, env=shell_env())`。

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
- eval 的验证子进程也复用同一套过滤。

**代价**：

- 某些需要环境变量的项目命令会失败。
- 用户需要在命令里显式传入必要变量。

**不要回归**：不要用 `inherit_env=True` 图省事。

## 11. model 字符串直接传给 create_deep_agent

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
- 传 `BaseChatModel` 实例会绕过 profile，丢失 provider 特有配置。

**代价**：

- provider 初始化错误会在 `create_deep_agent` 内部发生。
- 需要安装对应 provider 集成包，例如 `langchain-deepseek`。

**不要回归**：不要在 `build_agent` 里把字符串换成模型实例，除非明确接受 profile 行为变化。测试注入 `BaseChatModel` 是例外。

## 12. Rich 输出分工

**决策**：

- 进度、工具调用、thinking、错误：stderr
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

## 13. reasoning 单独走 stderr

**决策**：从 `content_blocks` 的 `reasoning` / `summary` / `non_standard` 和 `additional_kwargs.reasoning_content` 提取 reasoning，打印到 stderr；`--no-thinking` 关闭。

**原因**：

- 有些模型会返回 thinking，用户想看见，但它不应该混进最终回答。
- 不同 provider 的 reasoning block 形状不同，需要兼容。

**代价**：

- 解析逻辑分散在 `reasoning_text()`，需要跟着 provider 变化维护。
- stderr 内容增加。

**不要回归**：最终回答仍然只走 stdout；不要为了显示 thinking 把 reasoning 拼进 `message_text()`。

## 14. fixture evals + 可执行验证

**决策**：用 20 个离线 fixture 任务，agent 在临时 workspace 改代码，验证用 hidden tests / pytest / verify 脚本。

**原因**：

- 单元测试只能证明实现行为，不能回答「agent 能不能完成任务」。
- LLM judge 不稳定、不可复现；退出码更可靠。
- 同仓库小任务适合做回归信号。

**代价**：

- 有 API 成本和耗时。
- fixture、hidden tests、pricing 需要维护。
- 不是通用 benchmark，不能外推到任意仓库。

**不要回归**：

- 验证不要依赖 agent 能改到的配置；hidden tests 放在 workspace 外。
- 验证环境不要带 provider key。
- `bare` 失败不应让 `--baseline bare` 返回非零；`full` 失败要返回非零。

## 15. CI 质量门 + 手动 live 流程

**决策**：

- PR CI：`uv sync --locked`、ruff、format、mypy、pytest + coverage。
- live tests / live eval：仅 `workflow_dispatch`，需要 `DEEPSEEK_API_KEY`。

**原因**：

- 单元测试和静态检查便宜、稳定，适合每个 PR。
- 真实模型调用有成本、耗时、可能抖动，不适合 PR 阻塞。
- 密钥只放在仓库 secret，不进入代码。

**代价**：

- live 问题不会在 PR 自动暴露，需要手动跑。
- 覆盖率下限需要维护。

**不要回归**：

- 不要为了验证 CI 重跑 smoke。
- 不要把 live 测试加进 PR 工作流。
- 新增代码要带测试，不要靠降低 coverage 下限过 CI。

## 16. 提交/审阅身份分离

**决策**：

- 提交、推送、创建 PR：`Ashitaka-Bot`。
- 审阅、合并：号主账号最终执行。
- PR 回复身份按用户当前指令；本仓库当前要求使用 bot 回复。

**原因**：

- 自动化提交和 PR 创建可以用 App 身份。
- 审阅和合并需要明确责任人，不能由 bot 自审自合。

**代价**：

- 流程更繁琐；本地 git 身份和 bot 身份容易混。
- 需要 `$BOT` 工具和 `gh` 登录状态管理。

**不要回归**：不要在 `dev` / `main` 上直接提交；不要用 bot 代替审阅/合并。

## 当前开放问题

1. **审计日志 + secret 脱敏**：PR #16 已实现但未合并；合并后需要更新本目录。
2. **Windows shell 覆盖**：`del /s /q C:\`、PowerShell 删除等路径仍需更多测试。
3. **评测泛化**：20 个 fixture 任务是回归信号，不是通用能力证明。
4. **provider 安装**：是否把 provider 集成做成 extras，而不是默认依赖。
5. **许可证**：顶层 LICENSE 和 `pyproject.toml` 的 license 字段仍未定。
6. **长会话上下文**：目前依赖 Deep Agents summarization，是否需要更细的裁剪策略。

## 一句话总结

MiniCode 的设计哲学是：**薄封装、真实 workspace、明确边界、可读可测**。任何改动如果让边界更模糊，或者让「安全」变成文档口号而不是实际机制，都值得停下来重新讨论。
