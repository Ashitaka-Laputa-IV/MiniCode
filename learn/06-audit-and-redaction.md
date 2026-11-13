# PR #16：审计日志和脱敏加在哪一层

判断：PR #16 不改变一条命令能不能执行，它改变的是执行前后留下什么。审计把 `policy` / `approval` / `result` 写成 JSONL，脱敏在写日志和打印之前把明显的 secret 替换掉。它服务于排查和追责，不是新的权限层。

## 这段变更从哪来

PR #15 把权限模式、HITL 和 hard deny 合进 `dev` 之后，系统能拦住危险动作，但答不出三个问题：

- 拦了什么？只有终端上一次性的 `Blocked by permission policy`，没有持久记录。
- 谁批的？审批提示没有留下 approver、时间和决定。
- 结果如何？命令是否真的执行、exit code 是多少，没有结构化记录。

PR #16 就是补这条观察链。它没有改 `Policy` 的判定顺序，也没有改 HITL 的 resume 协议；它只增加两个模块，并在已有的执行点和审批点旁写事件。

## 新增的两个模块

[`audit.py`](../src/minicode/audit.py#L17) 只做一件事：把一条字典追加到 JSONL 文件。记录的基础字段在 [`AuditLogger.log()`](../src/minicode/audit.py#L38) 里固定：

```json
{
  "ts": "2026-11-13T17:00:00.123+08:00",
  "event": "policy",
  "session": "default",
  "mode": "ask",
  "actor": "Ashit"
}
```

`session` 来自 CLI 的 `thread_id`，`mode` 来自 `permission_mode`，`actor` 默认是 `getpass.getuser()`。事件类型只有三种：`policy`、`approval`、`result`。

[`redaction.py`](../src/minicode/redaction.py#L47) 也不改执行，它只负责把字符串里的 secret 换成 `***`。它同时被三处使用：审计记录、审批 UI、流式 tool args。三者共用同一套规则，避免“日志脱了、终端没脱”。

## 三类事件分别回答什么

`policy` 事件在 backend 真正执行前写，回答“这条 tool call 被怎么分类”：

```json
{
  "event": "policy",
  "tool": "execute",
  "decision": "deny",
  "reason": "command matched the hard deny-list",
  "args": {"command": "rm -rf /"}
}
```

`approval` 事件在 CLI 收集人类决定时写，回答“谁批的”：

```json
{
  "event": "approval",
  "tool": "execute",
  "decision": "approve",
  "approver": "Ashit",
  "reason": "user approved",
  "args": {"command": "uv run pytest -q"}
}
```

非 TTY 的拒绝也会写，但 `approver` 是 `null`，`reason` 是 `stdin is not a TTY`。

`result` 事件在 backend 执行后写，回答“结果如何”：

```json
{
  "event": "result",
  "tool": "execute",
  "ok": true,
  "duration_ms": 4210.3,
  "error": null,
  "exit_code": 0
}
```

文件工具不记内容。`write_file` 的 `policy` 事件只有 `file_path` 和 `content_bytes`，`result` 事件只有 `path` 和 `bytes`；`edit_file` 只记 `old_bytes` / `new_bytes`。这是有意的：审计要能追到文件和大小，但不要把源码或 secret 再复制一份。

## 一次 ask 审批实际怎么写

`uv run pytest` 不在 safe list 里，默认 `ask` 下会先 interrupt。用户批准后，事件顺序是：

```text
approval  approve
policy    ask          ← backend 仍然记录 Policy 的原始分类
result    ok / exit_code
```

这里最容易读错：`policy.decision` 不是“最终是否执行”，而是“执行前的策略分类”。`uv run pytest` 的分类是 `ask`，审批通过不等于分类变成 `allow`；真正执行由 backend 继续做。文件工具不同：`write_file` 在 ask 下先审批，批准后进 backend，backend 的 `allows_file_write()` 为真，所以它的 `policy` 事件是 `allow`。

用户拒绝时只有 `approval reject`，没有 `policy`/`result`，因为工具根本没进 backend。非 TTY 也是 reject，`approver` 为 `null`。读-only 的文件写入则是 `policy deny` 加 `result ok=false`；yolo 的 hard deny 也是 `policy deny` 加 `result exit_code=126`。

这些顺序由两处接线决定：

- [`ask_approval()`](../src/minicode/cli.py#L180) 在 TTY 分支和非 TTY 分支分别写 `approval`。
- [`PolicyShellBackend.execute()`](../src/minicode/backends.py#L64) 在 `evaluate_command()` 后写 `policy`，在 `super().execute()` 后写 `result`。

## 审计文件写到哪里

默认路径是 `<workspace>/.minicode/audit.jsonl`。CLI 在 [`main()` 的 audit 分支](../src/minicode/cli.py#L474) 创建 logger：

- `--audit-log <path>` 指定路径，相对路径按 workspace 解析；
- `--no-audit` 关闭；
- `MINICODE_AUDIT_LOG` 提供 shell 环境默认值；
- 没有指定时落到 `.minicode/audit.jsonl`。

`read-only` 模式仍然会写审计日志。这是安全记录，不是 agent 的文件改动；如果你要求“完全不写 workspace”，用 `--no-audit` 或 `--audit-log` 重定向。POSIX 上文件用 `0600`、新目录用 `0700`，见 [`AuditLogger.log()` 的文件创建](../src/minicode/audit.py#L49)；Windows 保留 ACL 继承。

审计写入失败是 fail-open：第一次失败打印 `minicode: audit log unavailable: ...`，之后继续执行工具，不阻断主流程。这个选择适合本地 CLI，但也意味着日志不是审计级保证；不要把它当成 tamper-proof 的合规记录。

## 脱敏流水线

[`redact_text()`](../src/minicode/redaction.py#L47) 的顺序是有意的：

1. URL 里的 `user:password@host` 先替换密码；
2. 已知 token 前缀（`sk-`、`ghp_`、`github_pat_`、`xoxb-`、`AKIA`、`AIza`）；
3. `Bearer ...`；
4. `Authorization: ...` 整行到换行；
5. `token=` / `password=` 这类赋值，支持 JSON/Python dict 的带引号 key；
6. `--api-key` / `--token` 这类 CLI 参数。

token 正则用 [`(?<![A-Za-z])`](../src/minicode/redaction.py#L10) 而不是裸匹配，目的是让 `disk-usage-report`、`risk-management`、`task-runner-2024` 保持原样，同时还能匹配 `"sk-..."`、`=sk-...`、`_sk-...`。这是一个 false positive 和 false negative 的取舍：审计日志的保真度也很重要，不能把所有带 `sk-` 的词都打成 `***`。

[`redact_value()`](../src/minicode/redaction.py#L67) 处理结构化参数：遇到 `token`、`password`、`secret`、`authorization` 这类 key，直接把 value 变成 `***`；其他值递归脱敏。这样即使模型传入的是 `{"token": "..."}` 而不是命令行字符串，也不会漏。

[`summarize_args()`](../src/minicode/redaction.py#L88) 是审计和终端共用的入口：

- `execute` 只保留脱敏后的 `command`；
- `write_file` 只保留 `file_path` 和 `content_bytes`；
- `edit_file` 只保留路径、old/new 字节数和 `replace_all`；
- `delete` 只保留路径；
- 未知工具按 key 递归脱敏，字符串截断到 200 字符。

[`display_args()`](../src/minicode/redaction.py#L120) 在审批 UI 里额外加 `content_preview`：先 `redact_text()`，再截 200 字符。顺序很重要；先截断再脱敏会让跨边界的 secret 只剩前缀，正则匹配不到。`tests/test_redaction.py` 的 195 个字符加 `_sk-...` 用例就是锁这个顺序的。

## 流式输出也走同一套

`print_update()` 在打印 tool call 时不再直接 `short_json(args)`，而是：

```python
short_json(summarize_args(name, args))
```

见 [`print_update()` 的 tool call 分支](../src/minicode/cli.py#L140)。这样 `-> execute {"command": "curl -H 'Authorization: Bearer ...'"}` 不会先把完整 header 打进终端 scrollback；审批提示再显示 `display_args()` 的脱敏版本。tool 结果 `<-` 仍然是截断后的原文，这是当前边界：PR #16 没有把工具输出也纳入脱敏。

## 读代码的五个停靠点

1. [`main()` 的 audit 分支](../src/minicode/cli.py#L474)：路径、`--no-audit`、session/mode 的创建点。
2. [`AuditLogger.log()`](../src/minicode/audit.py#L38)：基础字段、整条记录再脱敏、JSONL 追加、fail-open。
3. [`PolicyShellBackend.execute()`](../src/minicode/backends.py#L64) 和 [`write()`](../src/minicode/backends.py#L97)：`policy`/`result` 的真实写入点；文件工具在同一层处理。
4. [`ask_approval()`](../src/minicode/cli.py#L180)：approver、approve/reject、非 TTY 的 `approver=null`。
5. [`print_update()`](../src/minicode/cli.py#L113) 与 [`summarize_args()`](../src/minicode/redaction.py#L88)：终端参数为什么不再原样出现。

`agent.build_agent()` 只多了一个 [`audit` 参数](../src/minicode/agent.py#L142)，把它传给 backend；`run_turn()` / `interactive_loop()` 把它继续传给 `ask_approval()`。没有新的图节点，也没有新的中间件。

## 测试能证明什么

`tests/test_audit.py` 锁的是事件语义：

- [`test_audit_logger_creates_jsonl_with_common_fields`](../tests/test_audit.py#L26)：基础字段。
- [`test_read_only_write_logs_deny_and_result`](../tests/test_audit.py#L77)：read-only 写入的 deny + result，且日志里没有 `sk-` 原文。
- [`test_yolo_hard_deny_logs_reason_and_exit_code`](../tests/test_audit.py#L127)：yolo 下 hard deny 仍记 reason 和 126。
- [`test_ask_approval_logs_approver_and_redacted_args`](../tests/test_audit.py#L166)：approver 和脱敏参数。
- [`test_ask_approval_non_tty_logs_null_approver`](../tests/test_audit.py#L215)：非 TTY 的 `approver=null`。
- [`test_audit_logger_warns_once_when_unavailable`](../tests/test_audit.py#L63)：fail-open 只警告一次。

`tests/test_redaction.py` 锁的是边界，不是“有没有 `***`”：

- [`test_quoted_json_keys_are_redacted`](../tests/test_redaction.py#L59)：`{"token": "..."}` 这种 JSON payload。
- [`test_display_args_redacts_secret_across_preview_boundary`](../tests/test_redaction.py#L170)：先脱敏再截断。
- [`test_words_containing_sk_hyphen_are_not_redacted`](../tests/test_redaction.py#L194)：`disk-usage-report` 不误报。
- [`test_summarize_write_omits_content`](../tests/test_redaction.py#L106)：文件内容不落审计。
- [`test_summarize_unknown_tool_redacts_sensitive_keys`](../tests/test_redaction.py#L209)：结构化参数按 key 脱敏。

`tests/test_hitl.py` 的 [`test_run_turn_writes_approval_policy_result_chain`](../tests/test_hitl.py#L205) 把真实 interrupt/resume 和审计串起来，断言顺序是 `approval -> policy -> result`；[`test_read_only_write_writes_policy_deny_and_result`](../tests/test_hitl.py#L236) 断言 read-only 写入不会把 `hello` 写进日志。

## 改了会破坏什么

新增事件字段时，先问它会不会把文件内容或 secret 带进来。所有字段都会经过 [`redact_value()`](../src/minicode/redaction.py#L67)，但 `redact_value()` 不是万能解析器；不要把整段源码、环境变量或大块输出塞进 `args`。

新增一个会执行命令或写文件的工具时，审计不会自动覆盖它。你要么让它经过 `PolicyShellBackend`，要么自己在工具里写 `policy`/`result`；否则日志会缺失，且权限层也可能被绕过。

新增 token 规则时，至少加两条测试：一条 true positive（确实该脱敏），一条 false positive（普通词不该被改写）。`sk-` 的前导边界就是一个真实教训：去掉 `\b` 修跨边界，结果误伤 `disk-`/`risk-`/`task-`，最后用负向后顾收回来。

不要把 `audit.log()` 改成会抛异常的强依赖。当前 fail-open 是刻意的；如果未来要严格模式，应该是新的 `--audit-strict`，而不是悄悄改默认行为。

## 它没有做什么

- 不是 tamper-proof：本地追加文件，用户可以改、删、截断。
- 没有日志轮转、远程上报、加密或签名。
- 不保证识别所有 secret 格式；`execute` 的 command 仍可能内嵌 heredoc / `python -c` 的文件内容。
- 不记录文件内容，也不记录完整工具输出；未知工具的字符串只留前 200 字符。
- eval worker 不写审计日志；它是非交互的 yolo 子进程。
- `print_update()` 的 tool 结果 `<-` 仍然原样截断，不在脱敏范围。

## 判断规则

如果你在排查“为什么这条命令被拦”，看 `policy` 事件；如果你在排查“谁批准了它”，看 `approval.approver`；如果你在排查“最后有没有执行”，看 `result.ok` 和 `exit_code`。三件事不要混成一个问题。

如果你在改日志或脱敏，先问：这条数据会不会在三个月后仍然是 secret？会，就不要写进去；不会，再考虑字段名和截断长度。
