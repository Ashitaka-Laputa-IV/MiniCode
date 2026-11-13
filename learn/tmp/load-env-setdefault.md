# `load_env()` 里的 `setdefault` 是不是“原本有就不覆盖”

是。`os.environ.setdefault(key, value)` 的语义就是：如果 `key` 已经在 `os.environ` 里，返回原值，不写入；只有 key 不存在时才写入。

所以 [`load_env()`](../../src/minicode/cli.py#L40) 的行为是“shell 环境优先，`.env` 只补缺失项”。它的 docstring 也写的是 “without overriding the shell”，见 [`load_env()` 的 docstring](../../src/minicode/cli.py#L41)。

具体到 [`os.environ.setdefault(key, value.strip())`](../../src/minicode/cli.py#L47)：

- shell 里已有 `DEEPSEEK_API_KEY=from-shell`，`.env` 里写 `from-dotenv`：保留 `from-shell`。
- shell 里没有这个 key，`.env` 里有：写入 strip 后的值。
- `.env` 里的 key 不在 [`ENV_ALLOWLIST`](../../src/minicode/cli.py#L24)：不写入。
- `.env` 里的值是空串或纯空白：被 [`if value and value.strip()`](../../src/minicode/cli.py#L46) 跳过，不写入。
- shell 里已有这个 key 但值是空串：key 仍然“存在”，`setdefault` 不会覆盖；之后 `resolve_model()` 会把空值当没设置，回退默认模型，见 [`resolve_model()`](../../src/minicode/agent.py#L92)。

测试也锁了这几条：`test_load_env_does_not_override_shell`（[`tests/test_cli.py`](../../tests/test_cli.py#L289)）、`test_load_env_ignores_empty_values`（[`tests/test_cli.py`](../../tests/test_cli.py#L298)）、`test_load_env_strips_whitespace`（[`tests/test_cli.py`](../../tests/test_cli.py#L307)）。

一句话：已有环境变量不会被 `.env` 覆盖，包括空字符串；`.env` 只在 key 缺失且值非空、且在 allowlist 内时生效。
