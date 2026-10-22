# yechern’s skills

七个可独立安装的 agent 技能，用于任务恢复、全文阅读、小说世界书、数学研究和项目设计。

## 技能

- [durable-task](skills/durable-task/SKILL.md)：跨上下文保存进度、恢复工作，按需追踪证据版本与依赖。
- [durable-task-qwen-cloud](skills/durable-task-qwen-cloud/SKILL.md)：Qoder 移动端 Cloud 的上传、恢复、可选预算与 ZIP 交付。
- [progressive-reading](skills/progressive-reading/SKILL.md)：连续阅读小说正文，修订理解、定向回读并保存准确断点。
- [novel-worldbook](skills/novel-worldbook/SKILL.md)：将小说整理为可查阅的世界书；需同时安装 progressive-reading 和 durable-task。
- [palimpsest](skills/palimpsest/SKILL.md)：围绕证明障碍研究数学命题，探索证明与反例，区分实验、文本证明和形式证明。
- [gpt-human-style](skills/gpt-human-style/SKILL.md)：围绕实际目标改进项目与 skill，理清责任，集中 NOTICE 与 HELP，保留有用功能并删去冗余。
- [boundforge](skills/boundforge/SKILL.md)：用双循环探索数学界和最优值，记录论证、方向、依赖与恢复状态；包含 Python 程序、示例和测试。

## 安装与使用

下载 [最新发布](https://github.com/Ye-Chern/yechern-skills/releases/latest) 的 `yechern-skills.zip`，将需要的 `skills/<名称>/` 目录放入宿主支持的 skills 目录，保留内部结构并重新加载。也可以直接克隆仓库后复制目录。实际安装位置以宿主配置为准。

发布同时提供七个单项 ZIP 和 SHA-256 校验文件。使用 novel-worldbook 时，一并安装它的两个前置技能。Cloud 技能通过上传使用，步骤见 [UPLOAD.md](skills/durable-task-qwen-cloud/UPLOAD.md)。BoundForge 的配套程序需要 Python 3.10+，其他辅助脚本也只使用标准库。

可按下面方式开始：

> 使用 $durable-task 继续这项任务，复用现有进度记录，按实际需要选择记录方式。

> 使用 $novel-worldbook，先加载 $progressive-reading 与 $durable-task。原文在【路径】。请读完全文并整理世界书，允许全书剧透，笔记保持简短。

> 使用 $palimpsest 研究【命题】，保留原问题，给出证明、反例或明确的未解部分，并说明实际验证范围。

> 使用 $gpt-human-style 改进这个项目，保留核心能力，做出可运行或可审阅的结果。

> 使用 $boundforge 研究【下确界问题】，记录有用探索、论证与下一步，内外努力偏好按题目调整。

宿主不支持自动加载时，让模型读取对应入口及当前需要的引用材料。Python 辅助脚本只用标准库；阅读和数学技能也可使用当前环境已有的工具。

## 按任务决定记录方式

默认复用已有入口，或用一份 `work/state.md` 保存目标、进展、关键取舍或回退原因、下一步和验证方式。模型可选择方法、步骤、文件布局与记录频率；视觉、写作和交互任务可按作品反馈反复调整。

简记难以追踪关键依据、撤回影响或多层依赖时，再增加结构或使用账本。记录成本高时可以收简，保留恢复所需的依据与失效信息。事实与猜测、实际验证范围和用户授权仍须清楚。

用户要求的必达范围与可调的加工深度分开处理。例如，全文阅读任务可以减少笔记和边缘条目；尚有未读正文时，保存断点并保留原目标。

## 说明与验证

[使用说明](docs/usage.md)包含可选账本与 Cloud 命令；[兼容性说明](docs/compatibility.md)区分两套账本。它们的同名脚本和数据格式不能直接互换。

实际检查命令、运行结果和演练范围见 [验证记录](docs/validation.md)。安装、格式不匹配及特殊恢复见 [HELP](HELP.md)；通用能力与许可边界集中在 [NOTICE](NOTICE.md)，正常使用无需预先阅读。

## 许可与来源

[MIT](LICENSE)。技能来自个人任务实践，含模型辅助生成与修订；公开包保留工作方法和辅助工具，排除私人任务记录与小说原文。研究文献保留原作者署名与链接，相关权利归原作者。来源说明见 [SOURCES.md](SOURCES.md)。
