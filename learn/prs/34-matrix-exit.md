# PR #34：matrix 默认只做信息展示，不阻断 CI

一句话：`--baseline matrix` 是一个比较工具，不是发布门槛。这个 PR 让它默认即使有 baseline 失败也返回 0，想把它当门槛时再加 `--strict`。

## 问题在哪

矩阵会同时跑 `bare`、`deepagents-default`、`minicode-yolo`、`minicode-ask`、`minicode-no-checkpoint`、`minicode-no-subagents`。这些 baseline 的目的不同：

- `bare` 是能力下限，不编辑文件，失败很正常。
- `deepagents-default` 是框架对照，没有 MiniCode 的 `Policy` 和提示。
- `minicode-ask` 走 HITL，审批器是评测专用的。
- `minicode-no-checkpoint` 和 `minicode-no-subagents` 是消融对照。

把这些结果全都当成“代码坏了”，会让矩阵命令在正常实验里也返回非零。CI 或脚本一旦看到非零就停，矩阵就没法用来观察差异。

## 改法

`src/minicode/evals/cli.py` 在决定退出码时加了一个条件（[`evals/cli.py#L138`](../../src/minicode/evals/cli.py#L138)）：

```text
baseline == "matrix" and not strict -> 返回 0
```

`--strict` 打开后，非 `bare` 的 baseline 失败会让命令返回非零。`bare` 单独跑仍然返回 0，因为它是能力下限，不是“应该通过”的门槛。

报告本身不变，失败的任务、失败分类和每个 baseline 的通过数都还在。变的只是进程退出码。

## 怎么用

看差异，不让脚本失败：

```bash
uv run minicode eval --baseline matrix --runs 1 --json evals/results/smoke-matrix.json
```

把矩阵当门槛：

```bash
uv run minicode eval --baseline matrix --runs 1 --strict --json evals/results/smoke-matrix-strict.json
```

第二种适合你想确认“非 bare 的 baseline 没有退化”的时候。它仍然不把 `bare` 算进去。

## 边界

这不是“隐藏失败”。终端报告和 JSON 里仍然有失败信息，只是默认退出码为 0。真正需要阻断的场景应该显式加 `--strict`，不要依赖默认行为。

安全套件和恢复套件不受这个开关影响：它们有自己的套件入口，任何 case 失败仍然返回非零。

## 测试

`tests/test_evals_cli.py` 覆盖了三条路径：matrix 默认失败仍返回 0；matrix + `--strict` 返回非零；单独 `bare` 失败仍返回 0。这样以后改退出码逻辑时，不会把“信息展示”和“门槛”混回去。

## 读完后你应该能回答

1. 为什么 `bare` 失败不应当让 matrix 默认返回非零？
2. `--strict` 改变的是报告内容还是退出码？
3. 如果只想看差异、不想让脚本停，应该用哪个命令？
