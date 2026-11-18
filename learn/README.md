# MiniCode 学习笔记

判断：这组文档不介绍项目，而是把你放回改动现场。读完你应该能预测一次命令怎么走、找到该改的函数、判断代价；如果一篇文档删掉后这三种能力不变，它就不该存在。

## 30 秒索引

| 你的问题 | 先读 | 这篇给你的承诺 |
| --- | --- | --- |
| 我忘了系统怎么跑起来，边界在哪 | [`01-introduction.md`](01-introduction.md) | 用一条主线讲清定位、最短闭环和最危险的执行边界 |
| 我想改权限、审批或 shell 分类 | [`02-mental-model.md`](02-mental-model.md)、[`04-code-tour.md`](04-code-tour.md)、[`03-decisions.md`](03-decisions.md) | 先看清 interrupt 和 backend 的控制权，再找到 3 个改动点，再看代价 |
| 我想加工具、换 backend 或改执行路径 | [`04-code-tour.md`](04-code-tour.md)、[`03-decisions.md`](03-decisions.md) | 知道新工具必须经过哪一层，以及绕过后会破坏什么 |
| 我想跑评测、加 fixture 或读报告 | [`04-code-tour.md`](04-code-tour.md)、[`03-decisions.md`](03-decisions.md) | 分清 worker、verify、hidden tests 和退出码各自负责什么 |
| 我要审一段权限 PR | [`05-key-review.md`](05-key-review.md) | 用一个真实 diff 练“哪些命令该拦、哪些根本不在判定里” |
| 我想按 PR 读最近的变更 | [`prs/README.md`](prs/README.md) | 每个 PR 一篇，讲清问题、做法、边界和验证方式 |
| 我想理解状态、thread、checkpointer | [`02-mental-model.md`](02-mental-model.md) | 能画出一次请求的状态归属，知道 reset 到底删了什么 |

不要按序号硬读。第一次回来，先读 01 和 02；要动手时直接跳到对应篇目。

每篇只展开一个中心，不追求覆盖面：02 讲控制权和状态，04 讲调用栈，03 讲代价，05 讲审阅；`prs/` 只讲单个 PR 的变更，不重讲系统主线。遇到重复的事实，回到它第一次出现的那篇；后面的篇目只引用，不重讲。

文中的代码链接都指向“做决定的那一行”，不是 import 或空行；行号会漂移，符号名不会。读的时候如果链接和符号对不上，以符号名为准，并在 PR 里顺手修链接。

## 覆盖版本

文档描述 `learn` 合并 `origin/dev` 之后的代码基线 `c1bac6b`，learn 合并提交是 `f3133b0`，核对日期 2026-11-18。开始写之前执行过 `git fetch origin && git switch learn && git merge origin/dev`；这个提交就是合并后的代码状态。文档提交只新增/修改 `learn/` 文件，不改变代码，所以行号仍以 `c1bac6b` 为准。

当前 HEAD 包含权限模式、HITL、REPL/SQLite、评测矩阵、安全/恢复套件和 OpenCode Go 接入。PR #16 的审计日志/脱敏已被 #22 回滚，当前代码没有审计模块；这段历史见 [`prs/22-revert-audit.md`](prs/22-revert-audit.md)。没有合入 `dev` 的实验仍只能标为“计划中”。

`learn` 不需要合并回 `dev`；文档里的行为以当前 HEAD 的代码和测试为准，不以 README 或根目录 `AGENTS.md` 为准。

## 每篇怎么用

`01-introduction.md` 用来恢复边界感：它回答“MiniCode 到底做什么、不做什么、最危险的一条边界在哪”。如果你只想读一篇，读它。

`02-mental-model.md` 用来恢复主线：`main()` → `build_agent()` → 图 → tool call → `Policy`/HITL → `PolicyShellBackend` → stdout/stderr。它包含状态归属和三条不变量。

`03-decisions.md` 用来判断代价：七个选择按“问题/约束/选项/选择/代价/何时重审/证据”展开。不要在写代码前通读，遇到分歧时查对应决策。

`04-code-tour.md` 用来定位：12 个停靠点按调用顺序排，每站都写了为什么停、读什么、改了会怎样。它不替代读代码，只告诉你先看哪一段。

`05-key-review.md` 用来练审阅：以 `e0312de` 的真实 diff 为例，列出 8 个按风险排序的问题和答案，并在末尾写“表面审阅会漏掉什么”。

`prs/README.md` 是 PR 索引。每篇只讲一个已经合入的 PR：它解决什么问题、改了哪些位置、代价是什么、怎么验证。它不替代 01–05，也不把 PR 描述当事实；代码和测试仍然是最终依据。

## 验证与更新

当前 HEAD 上核对过 `uv run minicode --help` 和 `uv run minicode eval --help`。全量测试按下面的命令运行；本文不抄写通过数，因为测试数量会随 PR 变化，写死很快过期。需要具体数字时，以那次运行的终端输出或 CI 为准。

代码或行为变了，按这个顺序更新：

```bash
git fetch origin
git switch learn
git merge origin/dev
uv run python -m pytest -q
```

然后更新 `README.md` 里的 HEAD 和日期，逐个打开受影响篇目的行号链接，重跑该篇引用的命令。行号会漂移，符号名不会；如果链接漂了，用符号名搜索后再改锚点。

只改 `learn/`。如果文档里发现代码问题，写进文档，不改 `src/`、`tests/`、配置或 CI；发现需要新决策，先加一篇的证据，不要为了对称补一节。

判断规则：先按问题选一篇，不要按顺序读。读完如果你还不能用一句话说出“这次改动把哪条 tool call 送进了 `execute`”，回到 02 画一遍控制权。

如果只记住一件事：权限改动先看执行入口，输出改动先看 stdout/stderr；两者混在一起，审阅一定会漏。
