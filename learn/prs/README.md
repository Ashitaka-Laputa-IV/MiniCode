# 按 PR 读 MiniCode

这组文档按 PR 拆开讲，适合你已经知道系统主线、现在想弄清“这次到底改了什么”的时候读。它不替代 `01`–`05`：`01`–`05` 教你画控制权、找改动点、判断代价；这里只回答某个 PR 的问题、做法和边界。

当前代码基线是 `learn` 合并 `dev` 后的 `c1bac6b`，合并提交是 `f3133b0`。下面这些 PR 都已经在 `learn` 历史里，不是计划。

## 先看哪篇

| 你想知道 | 读这篇 |
| --- | --- |
| 为什么审计日志又没了 | [`22-revert-audit.md`](22-revert-audit.md) |
| 系统提示怎么跟权限模式对齐 | [`26-permission-prompts.md`](26-permission-prompts.md) |
| 中文 README、架构和权限文档从哪来 | [`27-project-docs.md`](27-project-docs.md) |
| 评测怎么做 baseline 矩阵和 pass@k | [`28-eval-matrix.md`](28-eval-matrix.md) |
| 为什么评测里要关掉 subagent | [`29-no-subagents.md`](29-no-subagents.md) |
| 安全评测怎么测 canary 泄漏 | [`30-security-suite.md`](30-security-suite.md) |
| 中断后怎么从 checkpoint 恢复 | [`31-recovery-suite.md`](31-recovery-suite.md) |
| 评测报告的指标和 `wrong_files` 怎么来的 | [`32-eval-report.md`](32-eval-report.md) |
| 怎么用 OpenCode Go 模型 | [`33-opencode-go.md`](33-opencode-go.md) |
| 为什么 matrix 默认不阻断 CI | [`34-matrix-exit.md`](34-matrix-exit.md) |

## 阅读顺序

第一次读，先看 `22` 和 `26`：它们一个解释“删掉了什么”，一个解释“提示怎么跟权限对齐”。然后按兴趣读评测五篇 `28`–`32`，最后看 `33` 和 `34`。

每组 PR 都有同一个结构：先给结论，再给改动位置，再给一条能复现的命令或测试。你不需要从头背；需要改代码时，回到对应 PR 看它当时为什么这么做。

## 证据规则

每条判断都尽量落在当前代码、测试或 merge diff 上。代码是事实来源，PR 描述只用来解释当时的取舍。PR #16 的审计实现已经被 #22 回滚，当前代码里没有 `audit.py` 和 `redaction.py`；`22-revert-audit.md` 会交代这段历史。

命令都在当前 `learn` HEAD 上核对过。涉及模型调用的评测命令会消耗 API，不要为了读文档反复跑。
