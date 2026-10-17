# 兼容性与账本边界

仓库提供两种工作流：通用 `durable-task` 用于本机长任务；`durable-task-qwen-cloud` 用于 Qoder 移动端 Cloud 的上传、恢复和交付。它们分别带有 `scripts/task_memory.py`，但这两个同名文件来自不同实现版本，账本格式、命令参数和配套恢复流程没有自动互通保证。运行命令时，始终使用与当前技能配套的脚本和引用文档。

通用账本按 `references/protocol.md` 使用 `init`、`resume`、`show`、`put`、`focus`、`audit` 等操作。Cloud 账本按 Cloud 技能的 `references/ledger.md` 使用；它将账本放在任务项目内，并由 `cloud_bundle.py` 生成和校验恢复 ZIP。Cloud 的预算和有限计时由 `work_budget.py` 与 `checkpoint_timer.py` 管理。这些记录不会启动常驻模型，也不会让普通 Python 进程发出模型消息。

Cloud 的旧通用账本迁移需通过 Cloud 版本的 `relocate` 明确检查复制后的项目布局及文件绑定。迁移失败时应保留原账本，查清缺失或字节变化；不要手动修改数据库、借换脚本改写哈希，或仅凭 ZIP 成功打包判断恢复状态正确。

Cloud 技能文档针对 Qoder 移动端 Cloud，包含其上传 ZIP、恢复和交付步骤。它不描述 Qoder CN CLI 的能力。该仓库没有对 Qoder CN CLI 安装、会话恢复、时限或后台执行做兼容性测试，因此这些能力应记为未验证。

两个技能都以 Python 标准库实现脚本。已检查的代码没有引入第三方 Python 包；这不代表所有 agent host 都自动支持技能安装、附件上传或后台回执。宿主工具和运行限制以当前环境实测为准。
