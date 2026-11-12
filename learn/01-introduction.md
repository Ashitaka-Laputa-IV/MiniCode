# MiniCode 简介

## 一句话

MiniCode 是一个基于 [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) harness 的本地 coding agent：给它一个 workspace 和一条任务，它会读文件、改代码、执行 shell、验证结果，并把过程打印到 stderr。

它支持两种运行方式：

- **单次任务**：`uv run minicode "fix the failing test"`
- **交互式 REPL**：`uv run minicode -i`，或在 TTY 下不带 prompt 直接运行

## 它解决什么问题

目标不是做完整 IDE，也不是通用聊天机器人，而是把「一个会使用工具的 coding agent」压到最小可读、可改、可测试的形态：

- 文件操作：`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`
- 命令执行：在 workspace 根目录运行 shell
- 任务规划与子 agent：由 Deep Agents harness 提供
- 会话记忆：REPL 使用 SQLite 持久化；单次任务默认不跨进程保留
- 权限控制：`read-only` / `ask` / `yolo` 三档，默认 `ask`
- HITL 审批：危险文件修改和 shell 命令会中断，等待 approve/reject
- 任务评测：20 个离线 fixture 任务，验证「是否真的改对了」
- 输出交互：Rich 进度、Markdown 最终回答、管道下保持原文
- 模型 reasoning：单独打到 stderr，可用 `--no-thinking` 关闭

## 快速开始

要求 Python 3.13 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
cp .env.example .env
```

在 `.env` 中填入默认模型 DeepSeek 的 key：

```dotenv
DEEPSEEK_API_KEY=sk-...
```

默认模型是 `deepseek:deepseek-flash`。需要换模型时：

```bash
uv run minicode --model deepseek:deepseek-reasoner "review this change"
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

## 权限模式先知道

默认 `ask` 模式会在工具真正执行前拦截：

| 模式 | 文件写入/删除 | shell | 网络 |
| --- | --- | --- | --- |
| `read-only` | 拒绝 | 只允许 safe allow-list | 拒绝 |
| `ask`（默认） | 审批 | safe 允许，其余审批 | 审批 |
| `yolo` | 允许 | 允许，但 hard deny 仍拦截 | 允许，但 hard deny 仍拦截 |

```bash
uv run minicode --permission-mode read-only "review this change"
uv run minicode --permission-mode yolo "fix the tests"
```

非 TTY 环境下，`ask` 不会阻塞等待输入，而是直接拒绝需要审批的动作。需要显式使用 `--permission-mode yolo` 或 `--shell-allow-list`。

## 当前能力

| 能力 | 说明 |
| --- | --- |
| 单次任务 | 一条 prompt，跑完即退出 |
| REPL | `/help`、`/reset`、`/exit`、`/quit` |
| 会话记忆 | REPL 使用 SQLite checkpointer；默认 `<root>/.minicode/checkpoints.sqlite` |
| 会话选择 | `--thread` 选择会话，`--db` 选择数据库文件 |
| 失败恢复 | 失败、Ctrl+C、`/reset` 会删除当前 thread，避免恢复未完成节点 |
| 文件工具 | 虚拟路径 `/` 映射到 workspace 根 |
| Shell | `PolicyShellBackend` 包装 `LocalShellBackend`，工作目录为 workspace 根 |
| 权限 | `read-only` / `ask` / `yolo`，默认 `ask` |
| HITL | `write_file`、`edit_file`、`delete`、`execute` 可中断审批 |
| 静态策略 | safe allow-list、hard deny-list、网络/变更分类 |
| 环境隔离 | shell 只继承 allowlist 中的变量，不继承 provider key |
| 评测 | `minicode eval`，20 个 fixture 任务，支持 `full` / `bare` baseline |
| CI | PR 跑 ruff、format、mypy、pytest + coverage；live 测试和 live eval 手动触发 |
| 输出 | 进度走 stderr，最终回答走 stdout；TTY 下 Markdown，管道下原文 |

## 最近的迭代发生了什么

旧版文档停在「没有 HITL、没有 CI、REPL 只存在内存」的阶段。现在的版本已经多了这些能力：

1. **REPL + SQLite checkpoints**：会话可以跨进程恢复，`--thread` / `--db` 可控制会话。
2. **任务评测**：`evals/` 里有 20 个 fixture 任务，验证的是可执行结果，不是模型自评。
3. **CI 质量门**：ruff、format、mypy、pytest + 70% coverage 下限。
4. **live 测试**：手动触发，真实调用 DeepSeek；不进 PR CI，避免成本和密钥问题。
5. **reasoning 输出**：模型 thinking 打到 stderr，最终回答仍只走 stdout。
6. **权限模式 + HITL**：`ask` 模式通过 LangGraph interrupt/resume 做审批；`read-only` / `yolo` 各有边界。
7. **安全策略加固**：safe 命令拒绝元字符和危险参数；hard deny 会剥离 `sudo`、`env`、shell `-c` 等包装。

审计日志和 secret 脱敏在 PR #16，尚未合入 `dev`；学习时不要把它当成现有能力。

## 不是什么

- **不是沙箱**：`PolicyShellBackend` 仍然以当前用户权限执行 shell；策略层只是 guardrail。
- **不是权限系统**：没有 OS 级隔离、资源限制或多租户隔离。
- **不是通用 benchmark**：`smoke` 是 20 个同仓库小任务，用于回归，不是对任意仓库的能力声明。
- **不是全自动安全审批**：`ask` 的审批结果依赖用户输入；非 TTY 会 fail closed。
- **不是只读工具**：默认就能改文件、跑命令；`read-only` 是显式模式。

## 技术栈

| 层 | 选择 |
| --- | --- |
| 包管理 | uv + `src/` layout |
| Agent harness | `deepagents` |
| 图运行时 | LangGraph |
| 模型调用 | LangChain；默认 `deepseek:deepseek-flash` |
| 文件/Shell 后端 | `deepagents.backends.LocalShellBackend` + `PolicyShellBackend` |
| 会话持久化 | `langgraph-checkpoint-sqlite` |
| CLI 输出 | Rich |
| 环境文件 | python-dotenv |
| 测试 | pytest + pytest-cov |
| 静态检查 | ruff + mypy |
| CI | GitHub Actions |

## 仓库地图

```text
src/minicode/
  __init__.py        # 导出 main
  __main__.py        # python -m minicode
  cli.py             # 参数、REPL、审批、输出、错误处理
  agent.py           # 模型/root/checkpointer/prompt/build_agent
  policy.py          # 权限模式、safe/network/mutating 分类、hard deny
  backends.py        # PolicyShellBackend
  evals/
    cli.py           # minicode eval 参数与退出码
    runner.py        # suite/task 加载、子进程、验证、报告
    worker.py        # 单个任务的 full/bare 执行
tests/
  test_agent.py      # 模型/路径/环境/prompt/checkpointer/HITL 配置
  test_policy.py     # 策略分类、绕过、hard deny
  test_backends.py   # backend 层拦截
  test_hitl.py       # 真实 interrupt/resume
  test_cli.py        # 参数、输出、REPL、审批提示
  test_sqlite.py     # SQLite 跨 agent 持久化
  test_evals*.py     # 评测 runner/CLI/worker
  test_live.py       # 真实模型，手动触发
evals/
  suites/smoke.toml  # 20 个任务
  tasks/<id>/        # fixture + prompt + 可选 hidden tests/verify
  pricing.toml       # 成本计算
learn/               # 本目录
```

## 推荐阅读顺序

1. 本文：知道它是什么、怎么跑、现在有哪些能力。
2. [心智模型](02-mental-model.md)：知道一次请求、一次审批、一次评测怎么流动。
3. [关键决策](03-decisions.md)：知道为什么这样设计，以及哪些约束不能随便改。
4. [代码导读](04-code-tour.md)：知道每个文件、每条路径从哪里进入。
5. [PR 演进史](05-pr-walkthrough.md)：把最近没看的 PR 补回来。
6. [复习计划与练习](06-study-plan.md)：用问题和练习确认自己真的看懂了。

## 常用验证

```bash
uv run pytest -q
uv run pytest -q --cov=minicode --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run minicode --help
```
