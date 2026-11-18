# PR #33：接入 OpenCode Go 模型

一句话：这个 PR 让 MiniCode 可以直接用 `opencode-go:<model-id>`，不需要改代码或另起一个 agent。默认模型仍然是 DeepSeek。

## 之前怎么选模型

`--model` 和 `MINICODE_MODEL` 接受 `provider:model` 字符串，默认是 `deepseek:deepseek-flash`。这能覆盖 LangChain 已知的 provider，但 OpenCode Go 不在默认映射里。要用它，只能自己构造 `ChatOpenAI` 再塞进 agent。

## 改法

`src/minicode/agent.py` 增加了 `resolve_chat_model()`（[`agent.py#L135`](../../src/minicode/agent.py#L135)）。它先走原来的 `resolve_model()`，然后检查前缀：

- 如果模型名是 `opencode-go:<model-id>`，就返回一个 `ChatOpenAI`。
- 否则原样返回字符串，交给 Deep Agents 的默认解析。

`ChatOpenAI` 的参数是固定的：

- `base_url = https://opencode.ai/inference/go/openai/v1`（[`agent.py#L27`](../../src/minicode/agent.py#L27)）
- `api_key` 来自 `OPENCODE_GO_API_KEY`
- 默认 header 里带 `x-opencode-session` 和 `User-Agent: minicode/0.1.0`
- `stream_usage=True`，这样 usage 能进评测报告

`OPENCODE_GO_SESSION` 是可选的。不设置时，每次启动生成 `minicode-<uuid>`；需要复现同一会话时，可以显式固定它。

## 怎么用

```bash
uv run minicode --model opencode-go:deepseek-v4.1-flash "fix the failing test"
```

需要先设置：

```bash
set OPENCODE_GO_API_KEY=...
```

也可以写进 `.env`，但 `.env` 只会应用 allowlist 里的变量。`OPENCODE_GO_API_KEY` 和 `OPENCODE_GO_SESSION` 已经加进 CLI 的 allowlist（[`cli.py#L35`](../../src/minicode/cli.py#L35)），不会被 base URL 之类的变量带进来。

缺少 key，或者 `opencode-go:` 后面没有模型 id，都会直接抛 `ValueError`。这是启动期错误，不会等到第一次模型调用才失败。

## 评测也走同一条路

`bare` 和 `deepagents-default` 这两个 baseline 原来直接拿模型字符串。现在 worker 也让它们经过 `resolve_chat_model()`，所以 `--model opencode-go:...` 在 smoke、矩阵和其他 baseline 里都能用。

`evals/pricing.toml` 补了 OpenCode Go 的价格。价格是会变的，报告里的成本只是估算；真实账单以 provider 为准。

## 代价和边界

新增了 `langchain-openai` 依赖。OpenCode Go 是外部服务，网络、限流和可用性都不由 MiniCode 控制。`x-opencode-session` 只是会话标识，不是认证；真正的认证是 `OPENCODE_GO_API_KEY`。

这个 PR 没有改默认模型，也没有改权限和 HITL。它只是多了一个模型入口。

## 测试

`tests/test_agent.py` 覆盖 `resolve_chat_model()` 的 OpenCode Go 分支：base URL、header、session 默认值和显式值、缺少 key、空模型 id。`tests/test_cli.py` 覆盖 `.env` allowlist 里的两个新变量；`tests/test_evals_worker.py` 确认 baseline 也会走这个解析函数。

## 读完后你应该能回答

1. `opencode-go:` 前缀是在哪一层被识别的？
2. 为什么 `.env` 里的 base URL 不会被应用，但 API key 会？
3. `OPENCODE_GO_SESSION` 固定和不固定分别适合什么场景？
