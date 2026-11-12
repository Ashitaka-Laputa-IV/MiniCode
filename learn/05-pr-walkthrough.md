# PR 演进史

这篇按时间线把 PR #1–#15 串起来，重点不是复述 diff，而是回答：

- 这个 PR 解决了什么问题？
- 它改了哪些文件？
- 如果现在重读，应该看什么？
- 它留下了什么约束或教训？

> PR #16（审计日志 + secret 脱敏）目前仍是开放状态，不属于 `dev` 现有能力；文末单独说明。

## 一张表先看全貌

| PR | 标题 | 主线 | 现在最该看什么 |
| --- | --- | --- | --- |
| #1 | scaffold uv project and agent config | 项目骨架 | `pyproject.toml`、目录结构 |
| #2 | add Deep Agents coding agent | 最小 agent | `agent.py`、system prompt、shell env |
| #3 | load env config from .env | 配置安全 | `cli.load_env()`、env allowlist |
| #4 | use rich for CLI output | 输出分层 | `print_update` / `print_final` |
| #5 | add interactive REPL | 交互会话 | `interactive_loop`、`/reset` |
| #6 | persist REPL conversations in sqlite | 会话持久化 | `SqliteSaver`、`--db` / `--thread` |
| #7 | add fixture task eval suite | 任务评测 | `evals/runner.py`、`worker.py` |
| #8 | merge dev into main | 发布同步 | 无代码，跳过 |
| #9 | add engineering quality gates | CI 质量门 | `.github/workflows/ci.yml` |
| #10 | add live model tests | 真实模型测试 | `tests/test_live.py`、手动 workflow |
| #11 | show model reasoning in CLI output | reasoning 输出 | `reasoning_text()`、`--no-thinking` |
| #12 | require owner identity for review and merge | 流程约定 | 提交/审阅身份分离 |
| #13 | cover eval CLI and worker | 评测测试 | `test_evals_cli.py`、`test_evals_worker.py` |
| #15 | add permission modes and HITL approvals | 权限与审批 | `policy.py`、`interrupt_on`、`run_turn` |
| #16 | add audit logging and secret redaction | 审计/脱敏（未合并） | 不属于 `dev`，见文末 |

## 阶段 0：先把项目跑起来（#1–#3）

### #1 scaffold uv project and agent config

**问题**：需要一个能安装、能运行、能放配置的最小 Python 项目。

**做了什么**：

- uv + `src/` layout；
- `pyproject.toml` 的 `[project.scripts]` 暴露 `minicode`；
- `.env.example`、`.gitignore`、基础目录；
- 最初的 agent 配置。

**读什么**：`pyproject.toml`、`src/minicode/__init__.py`、`src/minicode/__main__.py`。

**留下的约束**：

- 所有命令都通过 uv 跑，不依赖全局 Python；
- 入口是 `minicode:main`，所以 `__init__.py` 只做导出。

### #2 add Deep Agents coding agent

**问题**：只靠模型聊天不够，需要能读文件、改文件、跑 shell 的 coding agent。

**做了什么**：

- `agent.py` 的 `build_agent()`；
- `create_deep_agent(...)`；
- `SYSTEM_PROMPT`：虚拟路径、shell 类型、先读后改、完成后总结；
- `shell_env()`：过滤环境变量，不把 provider key 传给 shell；
- 单次任务 CLI。

**读什么**：`build_agent()`、`SYSTEM_PROMPT`、`SHELL_ENV_ALLOWLIST`。

**留下的约束**：

- 文件工具用虚拟路径 `/`，shell 用相对路径；
- prompt 只是建议，真正的边界要靠 backend/策略；
- `model` 字符串直接传给 harness，保留 provider profile。

### #3 load env config from .env

**问题**：用户不想每次 export key；但陌生仓库的 `.env` 又不能乱改 endpoint。

**做了什么**：

- `load_env()` 从当前目录/祖先目录找 `.env`；
- 只应用 `MINICODE_MODEL` 和已知 provider key；
- 忽略 `*_BASE_URL`、endpoint 类变量；
- shell 中已有变量优先；
- 空值和纯空白值忽略。

**读什么**：`cli.load_env()`、`ENV_ALLOWLIST`、`tests/test_cli.py` 的 load_env 测试。

**留下的约束**：

- `.env` 不是「把 shell 里所有变量都加载进来」；
- Azure endpoint/version 必须放 shell；
- 后续的 `MINICODE_PERMISSION_MODE` / `MINICODE_SHELL_ALLOW_LIST` 也只从 shell 读。

## 阶段 1：让它像一个可用的 CLI（#4–#6）

### #4 use rich for CLI output

**问题**：纯文本输出难读，但脚本又需要干净的 stdout。

**做了什么**：

- 进度、工具调用、错误走 stderr；
- 最终回答走 stdout；
- TTY 下用 Rich Markdown；
- 非 TTY 下输出原文。

**读什么**：`print_update()`、`print_final()`、`print_error()`。

**留下的约束**：

- `minicode "..." > notes.md` 必须得到模型原文；
- 不要在非 TTY 下渲染 Markdown；
- 工具结果摘要要截断，避免刷屏。

### #5 add interactive REPL

**问题**：单次任务每次都要重新建立上下文，不适合连续修改。

**做了什么**：

- `interactive_loop()`；
- `/help`、`/reset`、`/exit`、`/quit`；
- 失败/中断后 reset，避免恢复未完成节点；
- 当时使用 `MemorySaver`，进程退出即丢失。

**读什么**：`interactive_loop()`、`reset_thread()`、`run_turn()`。

**留下的约束**：

- REPL 才需要跨轮状态；
- 失败后不能复用未完成 thread；
- 交互命令要最小，不要变成复杂 shell。

### #6 persist REPL conversations in sqlite

**问题**：REPL 退出就丢上下文，长任务无法继续。

**做了什么**：

- `SqliteSaver`；
- 默认 db：`<root>/.minicode/checkpoints.sqlite`；
- `--db` 选择文件，`--thread` 选择会话；
- `resolve_db_path()`：相对路径相对 root，拒绝 `:memory:`；
- `close_checkpointer()`：正常/异常退出都关闭连接；
- 失败、Ctrl+C、`/reset` 删除当前 thread。

**读什么**：`build_checkpointer()`、`resolve_db_path()`、`close_checkpointer()`、`tests/test_sqlite.py`。

**留下的约束**：

- `.minicode/` 和 `*.sqlite*` 必须被 git 忽略；
- 并行 REPL 要不同 `--thread` / `--db`；
- SQLite 选项只用于 REPL，单次任务不允许 `--db` / `--thread`；
- 单次 `ask` 用 `InMemorySaver`，不是 SQLite。

## 阶段 2：证明它真的能做事（#7–#10）

### #7 add fixture task eval suite

**问题**：单元测试只能证明实现行为，不能回答「agent 能不能修好一个仓库」。

**做了什么**：

- 20 个 `evals/tasks/<id>/` fixture；
- `task.toml`、`prompt.md`、可选 hidden tests / verify.py；
- runner：复制 fixture、启动 worker、跑验证、汇总报告；
- worker：`full`（agent）和 `bare`（纯模型）两种 baseline；
- pricing、token usage、tool calls、pass@1；
- hidden tests 放在 workspace 外，验证时才复制。

**读什么**：`evals/README.md`、`runner.run_task()`、`runner.run_verify()`、`worker.run_full()`、`worker.run_bare()`。

**留下的约束**：

- 验证用退出码，不用 LLM judge；
- worker 环境有 provider key，验证环境没有；
- `bare` 是能力下限，bare-only 失败不返回非零；
- 不要把 smoke 说成通用 benchmark；
- smoke 有成本，PR CI 不跑。

### #8 merge dev into main

**问题**：把 `dev` 同步到 `main`。

**做了什么**：合并，没有新的代码逻辑。

**读什么**：不用读；知道发布分支关系即可。

### #9 add engineering quality gates

**问题**：没有 lint、类型检查、覆盖率，改动质量靠人眼。

**做了什么**：

- `.github/workflows/ci.yml`；
- `uv sync --locked`；
- ruff check / format check；
- mypy src；
- pytest + coverage，下限 70%；
- 上传 coverage artifact；
- live eval workflow（手动）。

**读什么**：`.github/workflows/ci.yml`、`pyproject.toml` 的 `[tool.ruff]` / `[tool.mypy]` / `[tool.coverage]`。

**留下的约束**：

- 新增代码要带测试；
- 不要靠降低 coverage 下限过 CI；
- PR CI 不调用模型；
- workflow 改动本地至少跑一遍对应命令。

### #10 add live model tests

**问题**：单元测试都用 fake model，无法发现真实 provider 的 tool calling / reasoning 兼容问题。

**做了什么**：

- `tests/test_live.py`；
- `pytest -m live`；
- 仅支持 DeepSeek；
- 需要 `DEEPSEEK_API_KEY`；
- 手动 workflow `live-tests.yml`；
- 回复必须精确是 `ok`（允许结尾标点）。

**读什么**：`tests/test_live.py`、`.github/workflows/live-tests.yml`。

**留下的约束**：

- live 测试不进 PR CI；
- 缺 key 直接 fail，不 skip；
- 有 API 成本，只在需要时手动跑。

## 阶段 3：输出、流程与安全（#11–#15）

### #11 show model reasoning in CLI output

**问题**：有些模型返回 thinking，用户想看见，但不能污染最终回答。

**做了什么**：

- `reasoning_text()` 兼容：
  - `content_blocks` 的 `reasoning`；
  - `summary` 列表；
  - `non_standard` thinking/reasoning；
  - `additional_kwargs.reasoning_content`；
- `print_update()` 把 thinking 打到 stderr；
- `--no-thinking` 关闭。

**读什么**：`reasoning_text()`、`print_update()`、`tests/test_cli.py` 的 reasoning 测试。

**留下的约束**：

- 最终回答只走 stdout；
- reasoning 不要拼进 `message_text()`；
- 多 block 用换行拼接。

### #12 require owner identity for review and merge

**问题**：提交可以自动化，但审阅/合并需要明确责任人。

**做了什么**：

- 文档约定：提交/推送用 bot，review/合并由号主最终执行；
- 这是流程变更，不是运行时逻辑；
- 当前用户对 PR 回复另有指令时，以用户最新指令为准。

**读什么**：`AGENTS.md` 的「提交身份」「审阅与合并身份」。

**留下的约束**：

- 不要让 bot 自审自合；
- 实际执行时以用户当前指令为准。

### #13 cover eval CLI and worker

**问题**：eval runner 有了，但 CLI 退出码、worker usage、tool limit 等缺少测试。

**做了什么**：

- `tests/test_evals_cli.py`；
- `tests/test_evals_worker.py`；
- 覆盖 full/bare、退出码、JSON、keep、usage、tool limit、失败记录。

**读什么**：这两个测试文件，配合 `evals/cli.py` 和 `worker.py` 读。

**留下的约束**：

- 评测代码也要有单元测试，不能只靠 smoke；
- fake model 要能控制 usage / tool calls / final；
- 退出码是契约的一部分。

### #15 add permission modes and HITL approvals

**问题**：默认直接执行危险命令，用户没有确认机会；read-only 也没有真正的只读保证。

**做了什么**：

- `policy.py`：
  - `read-only` / `ask` / `yolo`；
  - safe allow-list；
  - network / mutating / unknown 分类；
  - hard deny-list；
  - 引号感知切分；
  - wrapper 剥离（`sudo`、`env`、`command`、`nohup`、`exec`、`time`、shell `-c`）。
- `backends.py`：
  - `PolicyShellBackend` 拦截 hard deny；
  - read-only 拒绝文件写/编辑/删除。
- `agent.py`：
  - ask 模式 `interrupt_on`；
  - 文件工具总是中断；
  - `execute` 只在 `needs_approval` 时中断；
  - ask 单次任务用 `InMemorySaver`。
- `cli.py`：
  - `--permission-mode`、`--shell-allow-list`；
  - `ask_approval`、`resume_command`、`run_turn` 的 interrupt/resume；
  - 非 TTY fail closed。
- 测试：`test_policy.py`、`test_backends.py`、`test_hitl.py`。

**读什么**（如果只读一个 PR，读这个）：

1. `policy.evaluate_command()` 的顺序；
2. `policy._is_safe()` 和 `_is_hard_denied()`；
3. `agent.build_agent()` 的 `interrupt_on`；
4. `cli.run_turn()` 的 interrupt/resume；
5. `tests/test_policy.py` 和 `tests/test_hitl.py`。

**留下的约束**：

- hard deny 在 yolo 下仍生效；
- approve 不等于绕过 hard deny；
- 非 TTY 不能阻塞等待；
- read-only 的 shell 也只允许 safe；
- 策略是 guardrail，不是 sandbox；
- 任何新规则都要同时测「能拦」和「不误伤」。

## 如果只有时间读 3 个 PR

1. **#6 SQLite**：理解 checkpointer、thread、REPL 生命周期。
2. **#7 evals**：理解项目怎么证明自己真的能改代码。
3. **#15 权限/HITL**：理解默认安全边界和 interrupt/resume。

## 审阅主题回顾

这些 PR 的 review 里反复出现几类问题，读代码时可以带着它们：

- **测试是否覆盖真实路径**：fake model、真实 stream、非 TTY。
- **失败是否 fail closed**：审批、验证、缺少 key。
- **状态是否正确关闭**：SQLite 连接、临时目录、thread。
- **验证是否真的独立**：hidden tests 是否在 workspace 外，验证环境是否没有 provider key。
- **策略是否可绕过**：引号、wrapper、`&`、`$(...)`、危险参数。
- **成本是否可控**：live 测试和 smoke 不进 PR CI。
- **文档是否和代码一致**：旧文档里「没有 HITL」「MemorySaver」「deepseek-chat」都已经被新实现推翻。

## 附：PR #16（未合并）

PR #16 加的是：

- JSONL 审计日志：`policy` / `approval` / `result`；
- `--audit-log` / `--no-audit`；
- secret 脱敏：provider key、Authorization、URL 密码、JSON key 等；
- 文件内容不进入审计，只记 path / byte count；
- 审计写失败 fail-open。

它目前**不在 `dev`**。学习当前代码时：

- `cli.ask_approval()` 仍然直接显示 args；
- `print_update()` 仍然直接显示 tool args；
- 没有 audit logger；
- 没有 redaction 模块。

等 #16 合并后，再更新：
- `learn/02-mental-model.md` 的「安全边界」；
- `learn/04-code-tour.md` 的 `cli.py` / backend 部分；
- 本文的 PR 表和「未合并」说明。
