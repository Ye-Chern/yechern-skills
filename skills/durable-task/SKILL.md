---
name: durable-task
description: Carry out sustained tasks across context compaction and session handoffs using task-appropriate recovery notes and validation, with versioned evidence and dependency records when needed. Use when sustained work has interacting subproblems, retractions, or recovery needs; also when asked to improve this skill from actual usage. Skip routine short tasks.
---

# Durable Task — 长任务结构与恢复

为当前工作留下足够的信息，使恢复后能正确选择下一步。保留用户要求的必达范围；成本上升时先减少非必要加工。完成标准由用户决定。

## 选择记录方式

先复用项目已有入口。通常一份状态文件即可说明目标、当前进展、关键取舍、下一步和验收方法；引用已有证据，不复制整段历史。视觉、写作和交互任务可以边看效果边调整，保留选定版本、重要反馈与回退原因。

只有简记难以跟踪关键依据、撤回影响或多层依赖时，才增加索引或使用本技能账本。任务时长、文件数量或经历压缩本身不要求建账本；记录过重时可以收简。领域验收方式见 [profiles.md](references/profiles.md)。

## 开始、恢复与推进

1. 识别现有 README、状态、计划或日志，保留原目标并合并用户的新约束。只补会影响下一步的缺项；能独立推进的部分继续。
2. 恢复时核对当前版本和相关材料。使用本技能账本时，先运行 `python <skill>/scripts/task_memory.py resume --root <ledger>`，再读契约并按 ID 取回证据；需要检查严格完成记录时运行 `audit --root <ledger> --strict`。其他账本先读原工具协议。具体命令见 [protocol.md](references/protocol.md)。
3. 选择一个能解除阻断、验证脆弱前提或完成可验收产物的动作。保存影响后续判断的输入、结果、来源版本和范围；大结果留在可取回的文件中，入口只标明覆盖范围并链接相关部分。
4. 区分证据、结论、决定和待办。账本用稳定 ID 连接必要依赖；`accepted` 仅表示按记录的范围验收。文件或前提变化后复核受影响的结论，不能自动沿用旧结论。
5. 关键决定、反例、撤回、用户约束变化、阶段产物或预期中断会影响后续工作时，更新原入口及相关报告。细小试做可合并记录，继续推进任务。

## 交付与续接

按约定的目标和验收方式检查产物，说明已完成、尚未验证的范围，并留下可继续工作的入口。中断或超时后先核对已产生的结果；只有确认未执行、可以安全重复，或已处理副作用后才重试。无法确认时记录为未知并先查证。

恢复后若仍无法确定要交付什么、哪些依据有效、哪些被撤回或下一步如何验收，就定向读取相关材料，不能用摘要补出缺失事实。交接、迁移、异常恢复和长进程处理见 [HELP.md](HELP.md)。

## 持续改进

遇到真实恢复失败、重复劳动、误信旧证据或管理成本过高时，按 [evolution.md](references/evolution.md) 记录可复现观察，再依用户已有授权做窄范围、可回退的修改；无授权时只记录提案。需要理解设计取舍时读 [research.md](references/research.md)。

通用能力边界和记录原则见 [NOTICE.md](NOTICE.md)。
