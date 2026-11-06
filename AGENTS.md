# AGENTS.md

## 仓库现状

- Python 项目，使用 uv 管理（`pyproject.toml`、`uv.lock`、`.python-version` 固定 3.13）。
- 基于 Deep Agents harness：`src/minicode/agent.py` 用 `create_deep_agent` + `LocalShellBackend`；`src/minicode/cli.py` 是入口。有 pytest 测试，无 lint 或 CI。
- Agent 拥有当前工作区的文件读写和 shell 执行权限，没有 HITL 审批；shell 环境变量经过过滤，不继承 provider key。默认模型 `deepseek:deepseek-chat`，用 `--model` 或 `MINICODE_MODEL` 覆盖。
- 一律使用 uv，不要用 `pip` 或全局 Python；虚拟环境 `.venv/` 由 uv 管理，已加入 `.gitignore`。
- `dev` 已推送到 `origin`；PR 基分支为 `dev`，功能分支从 `origin/dev` 切出。

## 常用命令

- 同步依赖：`uv sync`
- 交互式 REPL：`uv run minicode`（TTY 下无 prompt 自动进入）或 `uv run minicode -i`；`/help`、`/exit`、`/quit`
- 单次运行：`uv run minicode "<task>"`
- 其他入口：`uv run python -m minicode "<task>"`
- REPL 会话状态在内存中，进程退出即丢失
- 模型：`--model <provider:model>` 或环境变量 `MINICODE_MODEL`；默认 `deepseek:deepseek-chat`，需要 `DEEPSEEK_API_KEY`
- 环境变量：CLI 自动加载当前目录或祖先目录的 `.env`，但只应用 `MINICODE_MODEL` 和已知 provider key，忽略 base URL/endpoint 类变量；shell 已有变量优先。`.env` 已被忽略，提交 `.env.example`，不要把真实 key 写入版本库
- 添加依赖：`uv add <pkg>`；开发依赖：`uv add --dev <pkg>`
- 更新锁文件：`uv lock`（升级用 `uv lock --upgrade`）
- 运行单个测试：`uv run pytest tests/test_cli.py::test_parser_defaults`；全量：`uv run pytest -q`
- 临时脚本：`uv run python -c "..."`

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
