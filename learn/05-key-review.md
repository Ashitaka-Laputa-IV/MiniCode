# 审一段权限变更：引号、分段和 wrapper

判断：这段 diff 把 safe 判断从原始字符串移到 `_syntax_view()`，同时把 hard deny 改成引号感知的 segment。它修掉了明显的绕过，但没有把 shell 变成解析器。审阅时先问“哪些字符还能被解释”，再问“哪些命令根本不在判定里”。

## 这段 diff 从哪来

PR #15 第一轮审阅发现了三类问题：`ls $(rm -rf ...)` 和 ``ls `rm ...` `` 能绕过 safe 判断；`find . -delete`、`rg --pre`、`git diff --output` 这类 safe 命令能写文件；hard deny 对整条字符串做 `\b` 匹配，误伤 `grep shutdown notes.md`，又漏掉 `rm -rf /*`。

`54ea742` 先修了元字符、危险参数、审批参数展示和 segment/token 判定。复审又发现引号内的 `(`、`)`、`&` 被当成真元字符，`sudo rm -rf /`、`bash -c 'rm -rf /'` 在 yolo 下仍能绕过，`_SAFE_ARG_DENY` 用子串匹配误伤 `cat docs/--output.md`。

`e0312de` 就是针对这三条 follow-up 的提交。下面的 diff 只保留影响判断的 hunk，完整提交可用 `git show e0312de -- src/minicode/policy.py` 看。

```diff
+def _syntax_view(command: str) -> str:
+    """Return command text with quoted literals blanked, keeping expansions."""
+    ...
+            # $ and backticks still expand inside double quotes.
+            result.append(char if char in "$`" else " ")
+    ...
+
+def _has_unsafe_arg(segment: str) -> bool:
+    for token in _tokens(segment):
+        lowered = token.lower()
+        if lowered in _SAFE_ARG_DENY:
+            return True
+        if any(lowered.startswith(arg + "=") for arg in _SAFE_ARG_DENY):
+            return True
+    return False
...
     def _is_safe(self, command: str) -> bool:
-        if _REDIRECT_PATTERN.search(command) or _SHELL_META_PATTERN.search(command):
+        view = _syntax_view(command)
+        if _REDIRECT_PATTERN.search(view) or _SHELL_META_PATTERN.search(view):
             return False
-        segments = _segments(command)
+        segments = _segments(view)
         if not segments:
             return False
-        for segment in segments:
-            if any(arg in segment.lower() for arg in _SAFE_ARG_DENY):
-                return False
+        if any(_has_unsafe_arg(segment) for segment in segments):
+            return False
```

## 问题按风险排序

### 1. 高：引号被清空后，`bash -c 'rm -rf /'` 还能被拦吗？

能。`_is_hard_denied()` 先用 `_syntax_view()` 做 raw pattern 匹配，这一步会忽略引号内的 `| sh`；但真正的 segment 判定用的是 [`_split_segments()`](../src/minicode/policy.py#L158)，它保留引号内的完整 payload。`_segment_hard_denied()` 看到 `bash` 的 `-c` 后，把 payload 递归送进 [`_is_hard_denied()`](../src/minicode/policy.py#L366)，此时 payload 没有外层引号，`rm -rf /` 会命中。

这条路径的测试在 [`test_hard_deny_unwraps_wrappers_and_home_targets`](../tests/test_policy.py#L181)，覆盖 `bash -c 'rm -rf /'`、`cmd /c 'format C:'`、`env sudo rm -rf /`。审这段 diff 时不要只看 `_syntax_view()` 的“清空”动作，要同时看它和 `_split_segments()` 的分工。

### 2. 高：`read-only` 会阻止 `cat ~/.ssh/id_rsa` 吗？

不会。`cat` 在 [`SAFE_COMMAND_PREFIXES`](../src/minicode/policy.py#L42) 里；`_is_safe()` 只检查重定向、元字符、危险参数和前缀匹配，不检查路径是否在 workspace 内。`cat ~/.ssh/id_rsa` 没有任何重定向或元字符，所以在 `read-only`/`ask`/`yolo` 下都是 ALLOW。

这是“read-only 等于不改状态，不等于保密”的实例。这个 diff 没有引入它，但审权限变更时最容易漏掉：你在看“写”的边界，攻击面可能在“读”。如果需求是隔离读取范围，需要 OS 级隔离或容器，不是再加一条 `Policy` 规则。

### 3. 高：`time -p rm -rf /` 在 yolo 下会被 hard deny 吗？

不会。`_strip_prefixes()` 只剥裸 `time`，见 [`_strip_prefixes()`](../src/minicode/policy.py#L306)：它把 `time` 从 token 列表里去掉后，下一个 token 是 `-p`，不是 `sudo`/`env`/`nohup`/`time`，循环就停了。`_segment_hard_denied()` 看到首 token 是 `-p`，不会把它当 `rm`，于是返回 false。

同样的情况还有 `nice rm -rf /`、`timeout 1 rm -rf /`、`xargs rm -rf /`：它们在 `read-only` 下仍会被“非 safe 命令”拦住，在 `ask` 下会要求审批，但在 `yolo` 下会直接执行。这不是 `e0312de` 的回归，是 wrapper 覆盖的边界；PR #15 的复审也承认 `xargs` 这类命令仍在 guardrail 外。

### 4. 中：`_has_unsafe_arg()` 用 token 比较解决了什么？

它解决的是子串误判。旧代码用 `any(arg in segment.lower())`，所以 `cat docs/--output.md` 会因为路径里包含 `--output` 被判成不安全；新代码用 [`_tokens()`](../src/minicode/policy.py#L239) 切开后比较完整 token，`cat docs/--output.md` 保持 ALLOW。

它仍然拦 `git diff --output=out.txt`，因为 `_has_unsafe_arg()` 对 `arg + "="` 前缀做了检查，见 [`_has_unsafe_arg()`](../src/minicode/policy.py#L246)。这个改动看起来只是“更精确”，实际影响的是误报率：误报太多，用户会习惯性批准，审批就失去意义。

### 5. 中：`_split_segments()` 和 `_syntax_view()` 是不是两套解析器？

是，而且是故意的。`_syntax_view()` 服务于 [`_is_safe()`](../src/minicode/policy.py#L457)、`_is_network()`、`_is_mutating()` 和 raw deny pattern：它要把引号内的字面量清空，避免 `cat 'a&b'` 被当成 shell 分隔符。`_split_segments()` 服务于 hard deny：它要保留 `bash -c '...'` 的 payload，不能在引号内切开。

代价是维护两套边界。新增一个元字符（比如 `!` 历史展开、PowerShell 的 `$()`）时，两处都要检查；只改一处，就会出现“safe 判断放行、hard deny 看不到”或反过来。审这类 diff 时，问题不是“为什么不用一个函数”，而是“新规则有没有同时覆盖两套视图”。

### 6. 中：`when=needs_shell_approval` 在 resume 时会不会改变主意？

`needs_shell_approval()` 只依赖当前 `Policy` 和 command，策略对象在一次运行里不变，所以同一个 command 在暂停和 resume 时会得到同一个答案。真正要对齐的是 decision 的顺序：一个 interrupt 里有多个 `action_requests` 时，[`ask_approval()`](../src/minicode/cli.py#L169) 按顺序 append decision，[`resume_command()`](../src/minicode/cli.py#L211) 原样送回；顺序错了，approve 可能落到另一个 action 上。

现有 `tests/test_hitl.py` 只覆盖一个 action 的 interrupt，多 action 的排序没有端到端测试。审 HITL diff 时，这是一个应该主动要测试的点，而不是等线上出现“批准了 A 却执行了 B”。

### 7. 低：为什么双引号里还保留 `$` 和反引号？

因为它们在双引号内仍会展开。`_syntax_view()` 的单引号分支把内容全部清空；双引号分支只保留 `$` 和反引号，见 [`_syntax_view()` 的双引号分支](../src/minicode/policy.py#L225)。这样 `cat "a & b"` 里的 `&` 被清空，`cat "x $(rm -rf /tmp/v)"` 里的 `$()` 仍然能被 `_SHELL_META_PATTERN` 抓到。

这是一个容易审反的细节：看起来“引号内都安全”，但双引号不是字面量。测试 `test_shell_metacharacters_are_not_safe` 覆盖了 `$()`、反引号和 `&` 的未加引号版本；双引号内的展开则依赖 `_syntax_view()` 的这条分支。

### 8. 低：这段 diff 的测试还缺什么？

缺三类：带选项的 wrapper（`time -p`、`nice`、`timeout`、`xargs`）、读取 workspace 外的 safe 命令（`cat ~/.ssh/id_rsa`）、多 action 的 interrupt 排序。它们不是同一个风险等级，但都属于“代码能跑、语义没锁”的空白。

补测试时不要只断言 `exit_code == 0/126`；同时断言 decision 的 action 和 reason。`test_policy.py` 的参数化用例就是这么做的，读起来比“只跑一遍命令”更能说明约束。

## 审这段 diff 的顺序

第一遍只看输入变化：`_is_safe()` 从原始 `command` 变成 `_syntax_view(command)`，这改变了“哪些字符算元字符”的答案。先确认这个变化没有让 hard deny 的 raw pattern 失效。

第二遍看两个切分器：`_split_segments()` 保留引号内 payload，`_segments(view)` 清空引号内字面量。它们服务不同判断，不能用一个替代另一个；新增元字符时两处都要检查。

第三遍看 wrapper：`sudo`、`env`、`command`、`nohup`、`exec`、`time` 被剥离，但 `time -p`、`nice`、`timeout`、`xargs` 不在列表里。这不是实现错误，是覆盖边界；审阅时要明确它是否可接受。

第四遍看测试：现有用例覆盖了引号、wrapper、危险参数和 hard deny 误伤，但没有覆盖带选项的 wrapper、workspace 外读取和多 action 排序。缺的测试比缺的代码更能说明边界。

## 这段 diff 的结论

它是净改进：修掉了引号字面量的误报，把危险参数从子串比较改成 token 比较，也让 `bash -c '...'` 的 payload 能被递归检查。它没有把 `Policy` 变成 sandbox，也没有解决读取范围和 wrapper 选项的问题。

如果今天重审，我会要求两条 follow-up 测试而不是改代码：`time -p rm -rf /` 在 yolo 下应为 DENY（当前是 ALLOW），多 action interrupt 的 decision 顺序应被端到端锁定。第一条会暴露已知缺口，第二条会防止审批错位。

## 表面审阅会漏掉什么

第一，看到“引号感知”就以为有了完整解析器。它只是把引号内的字面量清空，再按 segment/token 判断；wrapper 的选项、shell 方言、命令替换都可能在这层之外。

第二，看到“read-only”就以为读不到 secrets。它只限制写和非 safe 命令；`cat`、`grep`、`git show` 仍能读取用户有权限的任何文件。

第三，看到测试全绿就以为边界完整。现有测试覆盖的是已知绕过，不是所有绕过；`time -p` 和多 action 排序就是没有覆盖的例子。

第四，只审 diff 本身。权限变更还要看 backend 是否二次判定、`yolo` 是否仍在 hard deny 之后、非 TTY 是否 fail closed；这些不在 `_is_safe()` 的 hunk 里。

判断规则：审权限 diff 时，先写三条命令：一条应该被拦、一条应该放行、一条在 yolo 下仍应被拦。如果 diff 不能让你预测这三条的结果，就还没审完。
