# AGENTS.md

## 仓库现状

- Python 项目，使用 uv 管理（`pyproject.toml`、`uv.lock`、`.python-version` 固定 3.13）。
- 基于 Deep Agents harness：`src/minicode/agent.py` 用 `create_deep_agent` + `LocalShellBackend`；`src/minicode/cli.py` 是入口。测试用 pytest，静态检查用 ruff + mypy，CI 在 GitHub Actions。
- Agent 拥有当前工作区的文件读写和 shell 执行权限，没有 HITL 审批；shell 环境变量经过过滤，不继承 provider key。默认模型 `deepseek:deepseek-flash`，用 `--model` 或 `MINICODE_MODEL` 覆盖。
- 一律使用 uv，不要用 `pip` 或全局 Python；虚拟环境 `.venv/` 由 uv 管理，已加入 `.gitignore`。
- `dev` 已推送到 `origin`；PR 基分支为 `dev`，功能分支从 `origin/dev` 切出。

## 常用命令

- 同步依赖：`uv sync`
- 交互式 REPL：`uv run minicode`（TTY 下无 prompt 自动进入）或 `uv run minicode -i`；`/help`、`/reset`、`/exit`、`/quit`
- 单次运行：`uv run minicode "<task>"`
- 其他入口：`uv run python -m minicode "<task>"`
- REPL 会话持久化到 SQLite（默认 `<root>/.minicode/checkpoints.sqlite`）；`--db` 指定数据库文件，`--thread` 选择会话；失败/中断/`/reset` 会清空当前 thread
- 默认 thread `default`；同一 workspace 并行 REPL 要显式用不同 `--thread`/`--db`，避免 `database is locked` 或 checkpoint 交错
- `.minicode/` 和 `*.sqlite*` 已忽略；数据库包含对话和工具输出，不要提交
- 模型：`--model <provider:model>` 或环境变量 `MINICODE_MODEL`；默认 `deepseek:deepseek-flash`，需要 `DEEPSEEK_API_KEY`
- 环境变量：CLI 自动加载当前目录或祖先目录的 `.env`，但只应用 `MINICODE_MODEL` 和已知 provider key，忽略 base URL/endpoint 类变量；shell 已有变量优先。`.env` 已被忽略，提交 `.env.example`，不要把真实 key 写入版本库
- 添加依赖：`uv add <pkg>`；开发依赖：`uv add --dev <pkg>`
- 更新锁文件：`uv lock`（升级用 `uv lock --upgrade`）
- 运行单个测试：`uv run pytest tests/test_cli.py::test_parser_defaults`；全量：`uv run pytest -q`
- 覆盖率测试：`uv run pytest -q --cov=minicode --cov-report=term-missing`；下限 50%，配置在 `pyproject.toml`；新增代码需自带测试，不要靠降低下限过 CI
- live 测试：`uv run pytest -m live -q`；默认 `pytest` 不跑，仅支持 DeepSeek，需要 `DEEPSEEK_API_KEY`，缺 key 会失败，有 API 成本
- 代码检查：`uv run ruff check .`；格式检查：`uv run ruff format --check .`；格式化：`uv run ruff format .`
- 类型检查：`uv run mypy src`
- 任务评测：`uv run minicode eval --baseline full --json evals/results/smoke-full.json`；`--baseline all` 同时跑 `bare`；20 个 fixture 任务在 `evals/tasks/`
- 评测结果目录 `evals/results/` 已忽略；修改任务/runner 后先跑 `--task <id>` 再跑 smoke
- smoke 有 API 成本和耗时，PR CI 不跑；只在需要回归数据或改动 eval runner 时手动跑
- 临时脚本：`uv run python -c "..."`

## CI

- `.github/workflows/ci.yml`：push / PR 到 `dev`、`main` 时运行 `uv sync --locked`、ruff、format check、mypy、pytest + coverage（下限 50%）。默认排除 live 测试，不调用模型。
- `.github/workflows/live-eval.yml`：仅手动 `workflow_dispatch`，需要仓库 secret `DEEPSEEK_API_KEY`，运行 smoke 并上传 JSON 报告。不要在 PR 流程里触发。
- `.github/workflows/live-tests.yml`：仅手动 `workflow_dispatch`，运行 `pytest -m live`，需要仓库 secret `DEEPSEEK_API_KEY`，不在 PR 触发。
- 改动 workflow 后本地至少跑一遍对应命令；不要为了验证 CI 而重跑 smoke。

## 项目技能

- `.agents/skills/caveman/` 是项目级 skill（来源 `JuliusBrussee/caveman`），`skills-lock.json` 锁定来源和哈希。
- 需要精简输出时调用 `caveman` skill（或 `/caveman`）；说 “stop caveman” 或 “normal mode” 退出。除非用户要求，不要默认启用。
- 更新：`npx -y skills@latest update`。注意更新会整目录重拷贝 `.agents/skills/caveman/`，可能静默覆盖本地新增的 `LICENSE`、`NOTICE` 和 README 修改；更新后检查并补回。

## MCP

项目级 MCP 配置在 `opencode.json`，两个 LangChain 公共 HTTP 端点均无需鉴权：

- `docs-langchain`（`https://docs.langchain.com/mcp`）：概念指南、教程和产品文档。
- `reference-langchain`（`https://reference.langchain.com/mcp`）：API 参考、类/函数签名。

涉及 LangChain、LangGraph、LangSmith 的问题优先查这两个 MCP。查看状态用 `opencode mcp list`；重新添加用 `opencode mcp add <name> --url <url>`。

## 提交身份：必须使用 Ashitaka-Bot

本机全局 git 身份是个人账号，直接 `git commit` 会以个人身份提交。提交和推送必须通过本地 GitHub App 工具完成：

- App：`Ashitaka-Bot`（slug `ashitaka-bot`，owner `Ashitaka-Laputa-IV`，App ID `5467534`，installation `175142757`）
- 私钥：`C:\Users\Ashit\.config\ashitaka-bot\private-key.pem`
- 工具：`C:\Users\Ashit\.config\ashitaka-bot\bot.py`
- venv：`C:\Users\Ashit\.config\ashitaka-bot\.venv`

下文用 `$BOT` 代指：

```
C:\Users\Ashit\.config\ashitaka-bot\.venv\Scripts\python.exe C:\Users\Ashit\.config\ashitaka-bot\bot.py
```

`$BOT` 只是文档占位符，不能直接执行；按所用 shell 直接写完整路径。PowerShell 示例：

```powershell
& 'C:\Users\Ashit\.config\ashitaka-bot\.venv\Scripts\python.exe' 'C:\Users\Ashit\.config\ashitaka-bot\bot.py' whoami
```

cmd 示例：

```cmd
set "BOT_PY=C:\Users\Ashit\.config\ashitaka-bot\.venv\Scripts\python.exe"
set "BOT_SCRIPT=C:\Users\Ashit\.config\ashitaka-bot\bot.py"
"%BOT_PY%" "%BOT_SCRIPT%" whoami
```

关键约束：

- 私钥、token 和 `.config/ashitaka-bot` 下的任何内容都不得进入版本库。
- 首次在本仓库 push 前运行 `$BOT setup`，它会写入本仓库的 `credential.helper`。不要依赖裸 `git push`，始终用 `$BOT push`。
- `$BOT commit` 只执行 `git commit`，**不会执行 `git add`**；先自行暂存，再提交。
- `$BOT commit` 必须带 `-m` 或 `-F`，否则会打开编辑器导致卡住。
- `$BOT push` 遇到 ssh remote 会临时改走 https。
- 目标仓库默认从 `origin` 推断；推断失败会直接报错。可用 `--repo OWNER/REPO` 或环境变量 `ASHITAKA_BOT_REPO` 覆盖。不要用其他仓库的默认值猜测。
- `$BOT pr create` 默认 `--base dev`，`--head` 默认当前分支；会拒绝从 `dev`/`main`/`master` 发起，也拒绝 `head == base`。
- 不要在 `dev`、`main` 上直接提交。另起 `feat/...`、`fix/...` 等分支，PR 基分支为 `dev`。

## 标准提交流程

1. 确认/获取 `dev`，从它切分支：`git switch -c feat/<name> origin/dev`
2. 修改后暂存：`git add <files>`
3. 以 bot 身份提交：`$BOT commit -m "feat: ..."`
4. 以 bot 身份推送：`$BOT push -u origin feat/<name>`
5. 把 PR 标题和正文写入临时文件（不要提交这些文件），然后：
   `$BOT pr create --title-file <title.txt> --body-file <body.txt> --head feat/<name> --base dev`
6. 检查结果：`$BOT api GET /repos/{repo}/pulls/<number>`

常用检查（`$BOT` 按上文替换为完整命令）：

```text
$BOT whoami
$BOT setup                  # 每个仓库首次 push 前执行一次
$BOT api GET /repos/{repo}/pulls/29
```

`$BOT api` 的路径支持 `{repo}` 占位符；`pr comment <number> --body-file <file>` 可用于回复 PR。
