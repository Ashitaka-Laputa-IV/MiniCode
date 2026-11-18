# PR #29：加一个“没有 subagent”的评测口径

一句话：这个 PR 不是给产品加功能，而是让评测能回答“subagent 到底有没有帮忙”。它把 `task` 工具从模型可见的工具列表里拿掉，并且拦住绕过去的调用。

## 为什么要这个 baseline

Deep Agents 默认带一个 `task` 工具，模型可以把一部分工作交给子 agent。这个能力很强，但它会改变评测的含义：一个任务通过，可能是主 agent 自己做的，也可能是子 agent 做的。你没法从总通过率里判断 subagent 的贡献。

要比较，就需要一个除了 subagent 之外完全相同的口径。`minicode-no-subagents` 就是为此存在的：权限模式、checkpoint、系统提示都不变，只把 `task` 拿掉。

## 实现分两层

第一层是“别让模型看到”。`src/minicode/middleware.py` 里的 `NoSubagentsMiddleware`（[`middleware.py#L34`](../../src/minicode/middleware.py#L34)）在 `wrap_model_call` / `awrap_model_call` 里过滤 `request.tools`，把名为 `task` 的工具删掉。模型收到的工具列表里没有它，正常就不会调用。

第二层是“看到了也不能用”。如果模型仍然发了一个 `task` 调用，middleware 的 `wrap_tool_call` / `awrap_tool_call` 会返回一个错误 `ToolMessage`，而不是把调用放过去。`_rejection()`（[`middleware.py#L53`](../../src/minicode/middleware.py#L53)）负责构造这条错误消息。

只做第一层不够。工具列表是给模型的提示，不是硬边界；模型可能从历史消息、提示词或别的路径拼出一个调用。第二层保证即使发生，也不会真的启动子 agent。

## 接到 agent 和 baseline

`build_agent()` 增加了 `subagents: bool = True`（[`agent.py#L204`](../../src/minicode/agent.py#L204)）。为 `False` 时，它把 `NoSubagentsMiddleware()` 放进 `create_deep_agent` 的 `middleware` 列表。默认仍然是 `True`，所以普通 CLI 行为不变。

`baselines.py` 新增 `minicode-no-subagents`：和 `minicode-yolo` 一样是 yolo + checkpoint，但 `subagents=False`。它进入 baseline 注册表、矩阵和 worker 的 choices（[`baselines.py#L42`](../../src/minicode/evals/baselines.py#L42)）。live-eval workflow 也接受这个 baseline。

## 它测什么，不测什么

它测的是“去掉 `task` 之后，同一个任务还能不能过”。如果通过率明显下降，说明 subagent 在这类任务上有贡献；如果不变，说明主 agent 自己就能做，subagent 只是多一层开销。

它不测 subagent 的质量，也不证明 subagent 安全。被拿掉的只是 `task` 工具，其他工具、权限和 hard deny 都不变。这个 middleware 也不是安全边界，它只是评测隔离的一部分。

## 测试

`tests/test_agent.py` 覆盖了同步和异步两条路径：构造一个会调用 `task` 的模型，确认工具列表里没有 `task`，并且直接调用会收到错误 `ToolMessage`。`tests/test_evals_baselines.py` 确认 `minicode-no-subagents` 的权限模式是 yolo、checkpoint 开着、`subagents=False`，并且它在矩阵里。

## 读完后你应该能回答

1. 为什么只从工具列表里删掉 `task` 还不够？
2. `minicode-no-subagents` 和 `minicode-yolo` 唯一的区别是什么？
3. 这个 middleware 能不能当成安全控制？
