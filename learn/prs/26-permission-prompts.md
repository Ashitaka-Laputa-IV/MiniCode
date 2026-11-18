# PR #26：让系统提示和权限模式说同一件事

一句话：权限策略早就分 `read-only`、`ask`、`yolo` 三档，但系统提示里还留着“危险命令不需要确认”这种笼统说法。这个 PR 把提示改成按模式生成。

## 问题在哪

旧提示把“危险”和“不可逆”的 shell 命令写成默认会直接执行。实际行为不是这样：

- `read-only` 只允许安全读命令和 allow-list，不会给你改文件。
- `ask` 对 allow-list 之外的 shell 和写操作走 HITL，危险命令还有 hard deny。
- `yolo` 才跳过审批，但 hard deny 仍然生效。

提示和策略不一致，模型就会按提示去尝试一些本来会被拦下的动作，用户看到的是“它明明说可以”。这不是权限漏洞，但会让审批体验变差，也会让模型在 read-only 下反复提出修改。

## 改法

`src/minicode/agent.py` 增加 `mode_hint()`（[`agent.py#L95`](../../src/minicode/agent.py#L95)），按模式返回一段短的行动约束。`build_agent()` 在拼系统提示时把它放进 `{guidance}`，不再使用固定文案。

三档的意思现在写得很直白：

- **read-only**：先检查、再报告，不要改文件；shell 只用安全的只读命令或 allow-list 里的命令。
- **ask**：先读后写，改动尽量小；写完跑测试、lint 或构建；文件写入/删除和 allow-list 之外的 shell 需要审批；allow-list 内的命令直接执行；hard deny 的命令仍然直接拒绝；被拒绝的动作不要重试。
- **yolo**：跳过审批，但 hard deny 仍然生效；除非用户明确要求，不要做破坏性或不可逆的操作。

未知模式留了一段保守文案：“不要修改，先确认模式”。不过 `PermissionMode.parse` 对非法值是直接抛错的，所以正常解析路径走不到这个分支；它只是防御性兜底。

## 为什么只改提示还不够

提示是给模型看的，不是执行层。真正决定一条命令能不能跑的是 `Policy`、HITL middleware 和 `PolicyShellBackend`。这个 PR 没有改这些控制点，只改了模型收到的行动建议。

所以审阅这类改动时，先问“提示说的和策略做的是不是一致”，再问“有没有把提示当成安全边界”。后者永远是否定的。

## 测试

`tests/test_agent.py` 增加了三类断言：

- `test_mode_hint_matches_mode`：每个模式都必须包含自己的关键词。
- `test_mode_hint_read_only_does_not_request_changes`：read-only 的提示不能要求改文件。
- `test_build_agent_prompt_matches_permission_mode`：拼出来的系统提示里要有对应 `mode_hint`，不能残留 `{guidance}` 占位符，也不能再出现 `run without confirmation`。

最后一条是回归点：它专门防止旧文案被加回来。

## 代价和边界

提示变长了一点，每个模式多了一小段文字。这是有意的：模型需要知道当前模式的边界。真正的风险不在 token，而在以后改权限策略时忘了同步 `mode_hint()`。`docs/permissions.md` 已经把“权限行为变化时同步文档和测试”写成规则，提示文案也应该跟着这条规则走。

## 读完后你应该能回答

1. 为什么 read-only 下模型仍然可能“想”改文件，但实际改不了？
2. `mode_hint()` 和 `Policy.evaluate_command()` 各自负责什么？
3. 如果新增一个权限模式，最少要改哪几处？
