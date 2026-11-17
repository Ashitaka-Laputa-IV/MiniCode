# MiniCode

[![CI](https://github.com/Ashitaka-Laputa-IV/MiniCode/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/Ashitaka-Laputa-IV/MiniCode/actions/workflows/ci.yml)

[English](README.md) | 简体中文

基于 [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)
harness 的极简 coding agent。

它使用 harness 提供的文件工具、shell 执行、规划和子代理，在一个 workspace
里运行单次任务或交互式会话。

## 要求

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- 一个 LangChain 模型 provider 的 API key（默认 DeepSeek）

## 安装

```bash
uv sync
```

设置 provider key。默认模型是 `deepseek:deepseek-flash`。复制示例文件并填入 key：

```bash
cp .env.example .env
```

PowerShell：

```powershell
Copy-Item .env.example .env
```

`minicode` 会从当前目录或祖先目录加载 `.env`。只会应用 `MINICODE_MODEL` 和已知
provider key；`OPENAI_BASE_URL` 这类 base URL/endpoint 变量会被忽略。shell 中
已有的变量优先。Azure 的 `AZURE_OPENAI_ENDPOINT` 和
`AZURE_OPENAI_API_VERSION` 需要设置在 shell 中，不要写进 `.env`。也可以直接
导出：

```bash
export DEEPSEEK_API_KEY="..."
```

`.env` 已被 git 忽略；仓库中只提交 `.env.example`。

## 使用

单次任务：

```bash
uv run minicode "explain the repository structure"
uv run minicode --root ../other-project "fix the failing tests"
uv run python -m minicode "summarize AGENTS.md"
```

交互式 REPL（TTY 下不带 prompt 也会自动进入）：

```bash
uv run minicode
uv run minicode -i
uv run minicode -i --thread work --db .minicode/work.sqlite
```

REPL 内使用 `/help`、`/reset`、`/exit` 或 `/quit`。对话默认持久化到
`<workspace>/.minicode/checkpoints.sqlite`。用 `--db` 选择数据库文件，用
`--thread` 选择会话。`/reset` 会清空当前 thread；失败或中断的 turn 也会清空，
避免下一轮恢复未完成的节点。

默认 thread 是 `default`。同一个 workspace 中并行运行 REPL 时，它们会共享
thread 和数据库；请用不同的 `--thread` 和 `--db`，避免 `database is locked`
或 checkpoint 交错。

SQLite 选项只适用于交互式 REPL。数据库包含对话历史和工具输出。`.minicode/`
和 `*.sqlite*` 已被 git 忽略；删除数据库或使用 `/reset` 可以清理当前对话。

使用其他 provider/model：

```bash
uv run minicode --model deepseek:deepseek-reasoner "review this change"
```

需要先安装对应 provider 的集成包，例如 `uv add langchain-anthropic` 或
`uv add langchain-openai`。

如果模型输出 reasoning，MiniCode 会在工具调用和最终回答之前，以 dim
`thinking` 块打印到 stderr。stdout 仍然只包含最终回答。用 `--no-thinking`
关闭。

## 任务评测

`smoke` 套件包含 20 个离线 fixture 任务：bug 修复、补测试、重构、跨文件修改和
小型工程改动。

```bash
uv run minicode eval --baseline all --json evals/results/smoke-all.json
```

最新评测数据、token 和成本见英文 README 的
[Task evals](README.md#task-evals)（避免中英文两份数字漂移）。

这是一个 **smoke suite**，不是通用 coding benchmark。任务是小型、由本仓库
自己挑选的，数字只用于回归跟踪。验证隔离是约定级的：它能阻止配置绕过，但不
是对抗恶意 agent 的 sandbox。

任务定义在 `evals/tasks/`，suite 在 `evals/suites/smoke.toml`，runner 在
`src/minicode/evals/`。任务格式见 [`evals/README.md`](evals/README.md)。

## 开发

运行与 PR CI 相同的检查：

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q --cov=minicode --cov-report=term-missing
```

用 `uv run ruff format .` 格式化改动文件。覆盖率下限是 70%，配置在
`pyproject.toml`；新增代码应自带测试，不要靠降低下限过 CI。

Live 测试会调用真实模型，默认不运行：

```bash
uv run pytest -m live -q
```

它们需要 `DEEPSEEK_API_KEY`，目前只支持 DeepSeek 模型，缺少 key 会失败。Live
测试不属于 PR CI，只能在 Actions 中手动运行 **Live tests** workflow。

PR CI 只运行单元测试和静态检查，不调用模型。Live eval 是手动的：在 Actions
中运行 **Live eval** workflow（需要仓库 secret `DEEPSEEK_API_KEY`），或在本地
运行上面的评测命令。成本和细节见 [`evals/README.md`](evals/README.md)。

## 权限

MiniCode 默认使用 `ask` 模式。工具调用在执行前会经过权限策略：

- `read-only`：拒绝文件写入/删除和非安全 shell 命令。
- `ask`（默认）：文件写入/删除和风险 shell 命令需要审批；安全只读命令直接执行。
  没有 TTY 时，需要审批的动作会被拒绝，而不是阻塞等待。
- `yolo`：跳过审批，但 hard deny-list 中的常见灾难性命令仍会被拦截。

```bash
uv run minicode --permission-mode read-only "review this change"
uv run minicode --permission-mode yolo "fix the tests"
uv run minicode --shell-allow-list "git status,uv run pytest" "check the tests"
```

`MINICODE_PERMISSION_MODE` 和 `MINICODE_SHELL_ALLOW_LIST` 可以提供默认值；
`.env` 加载器只应用模型和 provider key。`--shell-allow-list` 还支持
`recommended` 和 `all`。

决策顺序、HITL、allow-list 细节和新增工具接入清单见
[权限与新增工具](docs/permissions.md)。

## 安全

Agent 使用 `PolicyShellBackend` 包装 `LocalShellBackend`：它可以读取和写入文件，
并以你的用户权限运行 shell 命令。权限模式和 hard deny-list 是 guardrail，
**不是 sandbox**；有意的命令仍然可能触达宿主机。只在可信 workspace 中使用，
不可信代码请使用容器或 VM。

shell 命令只继承过滤后的环境：常见 OS/PATH/temp 变量以及 Python、uv 路径。
Provider API key 不会继承到 agent 的 shell 命令中。

完整威胁模型、已知限制和漏洞报告方式见 [`SECURITY.md`](SECURITY.md)。

## 项目工具

- MCP server：`docs-langchain`、`reference-langchain`（配置见 `opencode.json` 和
  `.github/mcp.json`）
- 项目 skill：`.agents/skills/caveman/`（详见 `AGENTS.md`）

## 文档

- [中文文档索引](docs/README.md)
- [架构总览](docs/architecture.md)
- [权限与新增工具](docs/permissions.md)
- [SECURITY.md](SECURITY.md)
- [evals/README.md](evals/README.md)

## License

[MIT](LICENSE)
