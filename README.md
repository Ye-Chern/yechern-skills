# Durable Task

用于长任务恢复、证据绑定与依赖复核。包含两个技能：

- `durable-task`：通用工作流，组织恢复入口、版本化证据和依赖。当前实现为 I009。
- `durable-task-qwen-cloud`：Qoder 移动端 Cloud 的上传、恢复和 ZIP 交付流程。当前来源版本为 v0.2.1。

Python 脚本只依赖标准库。账本帮助恢复已记录的状态，不验证研究结论本身；Cloud 技能也不延长平台时限或保证环境持续运行。

## 安装通用技能

把 `skills/durable-task/` 整个目录复制到代理宿主支持的 skills 目录，保留相对结构，然后重新加载技能。例如 Codex 常用 `$HOME/.codex/skills/durable-task/`，实际位置以宿主配置为准。

也可从 [Releases](https://github.com/Ye-Chern/durable-task/releases/latest) 下载两个独立技能包及 SHA-256 校验文件。

Qoder 移动端 Cloud 的上传步骤和提示模板见 [`skills/durable-task-qwen-cloud/UPLOAD.md`](skills/durable-task-qwen-cloud/UPLOAD.md)。该技能包通过任务 ZIP 上传使用，不等同于 Qoder CN CLI 的安装或运行说明。

## 核心流程

通用技能先从任务现有 README、状态或计划恢复入口开始；新任务写清目标、验收、授权和输入。需要版本化账本时，可用以下命令初始化、恢复、读取证据和审计：

```text
python <skill>/scripts/task_memory.py init --root <ledger> --project <project> --contract <contract.md>
python <skill>/scripts/task_memory.py resume --root <ledger>
python <skill>/scripts/task_memory.py show --root <ledger> --id E1
python <skill>/scripts/task_memory.py audit --root <ledger> --strict
```

按需创建节点或更新前沿：`put --file <node.json>`、`focus --file <focus.json>`。通用账本字段和迁移限制见 [`docs/usage.md`](docs/usage.md)。

Cloud 技能提供另一套 `task_memory.py`，并附带预算、计时和恢复包工具。它有自己的 schema 和流程，当前不会自动与通用账本互通；不要交叉替换同名脚本。具体差异见 [`docs/compatibility.md`](docs/compatibility.md)。

## 验证范围

发布前通过 54 项脚本检查：通用版 24 项基础检查、13 项可靠性测试，Cloud 版 17 项测试。检查范围不包括模型恢复能力、研究结论或平台长期运行。Cloud v0.2.1 文档修订后未进行新的云端实测。命令与范围见 [验证说明](docs/validation.md)。

## 许可证

[MIT](LICENSE)。
