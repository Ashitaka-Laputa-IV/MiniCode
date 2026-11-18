# MiniCode 文档

这里是 MiniCode 的中文文档入口。英文 README 仍然是安装、命令和评测数据的
主入口；本目录解释系统怎么工作、权限在哪里生效，以及新增工具时不能漏掉什么。

## 阅读路径

| 你的问题 | 先读 |
| --- | --- |
| MiniCode 由哪些部分组成？一次任务怎么走完？ | [架构](architecture.md) |
| 三种权限模式分别允许什么？为什么命令会被拒绝？ | [权限与新增工具](permissions.md) |
| 新增一个会写文件或执行命令的工具，要改哪里？ | [权限与新增工具](permissions.md) |
| 我要报告安全问题，或者部署到不可信代码上 | [SECURITY.md](../SECURITY.md) |
| 我想跑评测或新增评测任务 | [evals/README.md](../evals/README.md) |
| 最近一次六基线、安全和恢复评测结果 | [2026-11-18 评测结果](results-2026-11-18.md) |
| 我要安装、运行或开发 | [README.zh-CN.md](../README.zh-CN.md) |

## 文档列表

- [架构总览](architecture.md)：组件图、一次 turn 的调用链、状态持久化、
  评测链路、代码地图和扩展点。
- [权限与新增工具](permissions.md)：`read-only` / `ask` / `yolo` 的决策顺序、
  HITL、allow-list、执行边界，以及新增工具接入清单。
- [SECURITY.md](../SECURITY.md)：威胁模型、已有防护、已知限制和漏洞报告方式。
- [README.zh-CN.md](../README.zh-CN.md)：安装、使用、REPL、评测和开发检查。
- [evals/README.md](../evals/README.md)：任务格式、运行方式和评测隔离边界。
- [2026-11-18 评测结果](results-2026-11-18.md)：六基线 pass@1/pass@3、
  相对 `minicode-yolo` 的消融、安全与恢复结果，以及失败分析。

## 维护约定

- 代码和测试是行为的最终事实来源；文档与代码冲突时，以代码为准，并在同一个
  PR 中修文档。
- 链接优先使用文件路径和符号名，不写容易漂移的行号。
- 权限模式、HITL 门控、allow-list 或 hard deny-list 变化时，同步更新
  [`permissions.md`](permissions.md) 和相关测试。
- 新增工具时，先读 [`permissions.md`](permissions.md) 的“新增工具接入清单”，
  不要让工具绕过 `PolicyShellBackend`。
- 图表使用 Mermaid，直接在 GitHub 上渲染，避免提交难维护的二进制截图。
