# Durable Task

用于长任务恢复。按任务需要保存状态，必要时追踪证据版本与依赖。包含两个技能：

- `durable-task`：通用工作流，组织恢复入口、版本化证据和依赖。当前修订为 I010。
- `durable-task-qwen-cloud`：Qoder 移动端 Cloud 的上传、恢复和 ZIP 交付流程。当前来源版本为 v0.2.2。

Python 脚本只依赖标准库。账本帮助恢复已记录的状态，不验证研究结论本身；Cloud 技能也不延长平台时限或保证环境持续运行。

## 安装通用技能

把 `skills/durable-task/` 整个目录复制到代理宿主支持的 skills 目录，保留相对结构，然后重新加载技能。例如 Codex 常用 `$HOME/.codex/skills/durable-task/`，实际位置以宿主配置为准。

也可从 [Releases](https://github.com/Ye-Chern/durable-task/releases/latest) 下载两个独立技能包及 SHA-256 校验文件。

Qoder 移动端 Cloud 的上传步骤和提示模板见 [`skills/durable-task-qwen-cloud/UPLOAD.md`](skills/durable-task-qwen-cloud/UPLOAD.md)。该技能包通过任务 ZIP 上传使用，不等同于 Qoder CN CLI 的安装或运行说明。

## 记录方式由任务决定

默认复用已有入口，或用一份 `work/state.md` 保存目标、当前进展、关键取舍或回退原因、下一步及验证方式。按需引用已有材料，不要求单独创建契约、日志或账本。

模型可以根据任务、工具和恢复风险选择方法、步骤、文件布局与记录频率。视觉、写作和交互任务可以反复看效果、判断和修改，保留有助恢复的版本与反馈；主观品味可以作为验收依据。无需为每次尝试或每个子问题建依赖。

当简记已难以追踪关键依据、撤回影响或多层依赖时，再增加结构或使用账本。任务长、文件多、模型能力不同，都不预设固定记录模板。工作中可以收简或增加结构，判断标准是能否可靠恢复，以及记录是否值得其成本。

自主选择记录方式仍需保留事实与猜测的区别、重要失效信息、实际验证范围和用户授权。依据变化时，复核受影响的重要结论。

## 可选账本

需要版本化账本时，可用以下命令初始化、恢复、读取证据和审计：

```text
python <skill>/scripts/task_memory.py init --root <ledger> --project <project> --contract <contract.md>
python <skill>/scripts/task_memory.py resume --root <ledger>
python <skill>/scripts/task_memory.py show --root <ledger> --id E1
python <skill>/scripts/task_memory.py audit --root <ledger> --strict
```

按需创建节点或更新前沿：`put --file <node.json>`、`focus --file <focus.json>`。通用账本字段和迁移限制见 [`docs/usage.md`](docs/usage.md)。

Cloud 技能提供另一套 `task_memory.py`，并附带预算、计时和恢复包工具。它有自己的 schema 和流程，当前不会自动与通用账本互通；不要交叉替换同名脚本。具体差异见 [`docs/compatibility.md`](docs/compatibility.md)。

## 验证范围

发布前通过 54 项脚本检查：通用版 24 项基础检查、13 项可靠性测试，Cloud 版 17 项测试。检查范围不包括模型恢复能力、研究结论或平台长期运行。本次为记录方式的文档修订，未进行新的 Qoder Cloud 实战复测。命令与范围见 [验证说明](docs/validation.md)。

## 许可证

[MIT](LICENSE)。
