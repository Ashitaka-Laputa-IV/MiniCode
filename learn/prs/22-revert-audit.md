# PR #22：把审计日志回滚掉

一句话：这个 PR 把 PR #16 加进来的审计日志和脱敏整套撤回了。当前 `learn` 里没有 `audit.py`，也没有默认的 `.minicode/audit.jsonl`。

## 它撤回了什么

PR #16 曾经在 agent、backend 和 CLI 之间加了一条审计链路：每次策略判断、审批和工具结果都写进 JSONL，默认位置是工作区的 `.minicode/audit.jsonl`。它还想在写盘前对 secret 做 best-effort 脱敏，文件工具只记路径和字节数，不记内容。

PR #22 是 #16 合并提交的精确反向提交：11 个文件，`+23 / -1101`。删掉的内容包括：

- `src/minicode/audit.py`
- `src/minicode/redaction.py`
- `tests/test_audit.py`
- `tests/test_redaction.py`
- `agent.py`、`backends.py`、`cli.py` 里的审计接线
- CLI/HITL 测试里的审计断言
- README 和 AGENTS 里的审计说明

所以如果你在旧笔记里看到“默认写审计日志”，那是 #16 时期的行为，不是现在。

## 为什么撤

PR 描述给了两个理由，都是产品边界问题，不是实现写错了。

第一，审计默认开启，连 `read-only` 模式也会往用户仓库里写 `.minicode/audit.jsonl`。`read-only` 的承诺是“不改用户文件”，但审计文件也是文件。用户没有显式同意，仓库里就多了一个隐藏目录，这个行为很难解释。

第二，当时同时存在三套审计思路：#16 的 `audit.py`、#18 的 `experiment/tracekit-audit`，以及 `experiment/nemo-relay` 的 ATOF 转 JSONL。它们记录的内容、格式和生命周期都没有收敛。与其把一套还没定型的方案默认打开，不如先撤回。

实现没有丢。PR 描述说代码保留在 `feat/audit-log` 分支的 `1612148`，以后可以按 opt-in 的方式回来。

## 现在是什么状态

当前 HEAD 上：

- 没有审计日志模块。
- `read-only` 不会因为审计而写文件。
- 也没有“事后可查的本地审计记录”这个能力。
- `learn/06-audit-and-redaction.md` 已经删除，因为它描述的是不存在的代码；历史由这篇文档承担。

如果你要重新引入审计，PR 描述里给了三个方向：默认关闭，只有显式 `--audit-log` 才写；日志路径不要默认落在用户仓库里，或者至少被 gitignore；脱敏逻辑应该是独立、可复用的模块，不要和审计写盘绑死。

## 证据和验证

看反向提交的范围：

```bash
git show --stat ed1ad89
git log --all --oneline -- src/minicode/audit.py
```

第一条会看到审计相关文件被删除，第二条能看到实现曾经在哪些提交里存在。当前代码里搜 `audit` 只剩文档和历史提交，不再有运行时入口。

## 读完后你应该能回答

1. 为什么“默认开启的审计”会和 `read-only` 的承诺冲突？
2. #22 是删掉了实现，还是只关掉了开关？
3. 如果以后要加回审计，默认行为应该是什么？
