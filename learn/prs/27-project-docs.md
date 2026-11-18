# PR #27：把项目文档补成一套能读的东西

一句话：这是一个纯文档 PR，把中文入口、架构、权限、安全策略和协作规则补上了。没有改运行时行为。

## 它解决了什么

在这之前，项目的主线信息散在 README、AGENTS 和代码注释里。新回来的人要先读一遍 `agent.py` 和 `cli.py`，才能知道：

- 一次任务从哪个入口进来，经过哪些层。
- 权限模式、HITL、allow-list 和 hard deny 的先后顺序。
- 加一个新工具时，哪些边界不能绕。
- 安全问题该怎么报，哪些风险是已知的。

PR #27 把这些内容拆成四份，各管一件事：

- [`README.zh-CN.md`](../../README.zh-CN.md)：中文安装、使用、REPL、评测和开发检查。
- [`docs/architecture.md`](../../docs/architecture.md)：组件图、入口、一次 turn 的调用链、状态归属、评测链路和代码地图。
- [`docs/permissions.md`](../../docs/permissions.md)：三种权限模式的决策顺序、HITL、allow-list、执行边界，以及“新增工具前的接入清单”。
- [`SECURITY.md`](../../SECURITY.md)：威胁模型、已有保护、已知限制和报告路径。

另外新增 [`docs/README.md`](../../docs/README.md) 作为中文文档入口，并在根 `AGENTS.md` 里加了文档入口。

## 为什么不是把 README 写长

README 是“怎么用”，架构文档是“为什么这样分层”，权限文档是“改这里会破坏什么”，安全策略是“哪些事本来就不保证”。这四件事的读者和更新时机不同，塞进一个文件会变成谁都不想维护的长文。

`docs/architecture.md` 里有一张组件图，但真正有用的是它把一次 turn 的顺序写清楚了：CLI 装配 agent，模型产生 tool call，`Policy`/HITL 决定能不能执行，`PolicyShellBackend` 再落到 shell，最后结果回到 stdout/stderr。你读代码时可以用这张图对位置。

`docs/permissions.md` 里的“新增工具接入清单”是给改动者用的：新工具如果绕开 `PolicyShellBackend` 或文件写入拒绝，就等于绕开了现有 guardrail。这个清单不是装饰，它把“加工具”从“注册一个函数”变成了“说明它经过哪一层”。

## 代价和边界

文档本身不会执行，所以这个 PR 没有新增测试。它的风险是漂移：权限、HITL、allow-list 或 hard deny 一改，文档就可能过期。PR 里把规则写成了“代码和测试是最终事实来源；权限行为变化时同一个 PR 更新文档和测试”。

这条规则比文档本身重要。你以后看到文档和代码不一致，先信代码，再修文档；不要为了让文档“看起来完整”去改代码。

## 验证

这是文档 PR，最直接的验证是打开文件看链接和命令：

```bash
uv run minicode --help
uv run minicode eval --help
```

命令能跑，说明 README 里的入口没写错。架构和权限部分则要回到 `src/minicode/agent.py`、`policy.py`、`backends.py` 对照符号名，不能只读文字。

## 读完后你应该能回答

1. 新增一个工具时，为什么不能只注册工具函数？
2. 架构文档和权限文档各自回答什么问题？
3. 文档和代码冲突时，以谁为准？
