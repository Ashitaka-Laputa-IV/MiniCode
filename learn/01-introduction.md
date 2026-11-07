# MiniCode 简介

## 一句话

MiniCode 是一个基于 [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) harness 的最小 coding agent：给它一个 workspace 和一条任务，它会读文件、改代码、执行 shell、验证结果。

它支持两种使用方式：

- **单次任务**：`uv run minicode "fix the failing test"`
- **交互式 REPL**：`uv run minicode -i`，或没有 prompt 时在 TTY 下自动进入

## 它解决什么问题

它不是另一个完整 IDE，也不是通用聊天机器人。目标是把「一个会使用工具的 coding agent」压到最小可读、可改、可测试的形态：

- 文件操作：`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`
- 命令执行：在 workspace 根目录运行 shell
- 任务规划与子 agent：由 Deep Agents harness 提供
- 会话记忆：REPL 内跨轮保留，退出即丢失
- 输出交互：Rich 进度、Markdown 最终回答、管道下保持原文

## 快速开始

要求 Python 3.13 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
cp .env.example .env
```

在 `.env` 中填入默认模型 DeepSeek 的 key：

```dotenv
DEEPSEEK_API_KEY=sk-...
MINICODE_MODEL=deepseek:deepseek-chat
```

运行：

```bash
uv run minicode "explain the repository structure"
uv run minicode --root ../other-project "fix the failing tests"
uv run minicode -i
```

也可以直接用模块入口：

```bash
uv run python -m minicode "summarize AGENTS.md"
```

## 当前能力

| 能力 | 说明 |
| --- | --- |
| 单次任务 | 一条 prompt，跑完即退出 |
| REPL | `/help`、`/reset`、`/exit`、`/quit` |
| 会话记忆 | REPL 使用 `MemorySaver` + `thread_id`；进程退出即丢失 |
| 失败恢复 | 单轮失败或 Ctrl+C 后轮换 thread，避免恢复未完成节点 |
| 文件工具 | 虚拟路径 `/` 映射到 workspace 根 |
| Shell | `LocalShellBackend`，工作目录为 workspace 根 |
| 环境隔离 | shell 只继承 allowlist 中的环境变量，不继承 provider key |
| 配置 | `.env` 自动加载，但只应用 `MINICODE_MODEL` 和已知 provider key |
| 输出 | 进度走 stderr，最终回答走 stdout；TTY 下渲染 Markdown，管道下输出原文 |

## 不是什么

- **不是沙箱**：`LocalShellBackend` 会以当前用户权限执行任意 shell 命令。
- **没有 HITL 审批**：没有 `interrupt_on` / approve / resume 流程；破坏性命令不会自动等待确认。
- **没有静态命令策略**：截至本分支，没有针对 `rm -rf`、`git push --force` 等模式的内置拦截。
- **不是任务成功率评测**：当前测试验证的是实现行为，不是“模型完成真实任务的比例”。

> 注：仓库的 `tmp` 分支里有 guard、trace、model-free evals 等实验性自改内容，但它们**不属于本分支**。本目录只描述 `dev` 上的实现。

## 技术栈

| 层 | 选择 |
| --- | --- |
| 包管理 | uv + `src/` layout |
| Agent harness | `deepagents` |
| 图运行时 | LangGraph |
| 模型调用 | LangChain；默认 `deepseek:deepseek-chat` |
| 文件/Shell 后端 | `deepagents.backends.LocalShellBackend` |
| CLI 输出 | Rich |
| 环境文件 | python-dotenv |
| 测试 | pytest |

## 仓库地图

```text
src/minicode/
  __init__.py      # 导出 main
  __main__.py      # python -m minicode
  cli.py           # 参数、REPL、输出、错误处理
  agent.py         # 模型、root、shell env、system prompt、build_agent
tests/
  test_agent.py    # 模型/路径/环境变量/checkpointer
  test_cli.py      # 输出、REPL、参数、错误路径
learn/             # 本目录：学习与导读
```

## 推荐阅读顺序

1. 本文：知道它是什么、怎么跑。
2. [心智模型](02-mental-model.md)：知道一次请求在系统里怎么流动。
3. [关键决策](03-decisions.md)：知道为什么这样设计，以及哪些约束不能随便改。
4. [代码导读](04-code-tour.md)：知道每个文件、每条路径从哪里进入。

## 常用验证

```bash
uv run pytest -q
uv run minicode --help
uv run minicode "Reply with exactly: ok. Do not use any tools."
```
