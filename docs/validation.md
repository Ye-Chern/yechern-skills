# 验证记录与限制

2026-10-17，发布前在 Windows、Python 3.12 上运行了三个套件，合计 54 项脚本检查：通用账本 24 项基础检查、13 项恢复可靠性测试，Cloud 版 17 项测试。该数量不是模型实验次数。

Cloud 脚本测试记录为 17 项通过，使用临时目录，未联网、未调用模型、未使用手机，也没有长等待。可在仓库根目录运行：

```text
python -B -m unittest discover -s skills/durable-task-qwen-cloud/tests -v
```

通用脚本的检查主要位于 `skills/durable-task/scripts/test_memory.py` 和 `test_reliability.py`。其中可靠性回归使用合成临时项目；可从仓库根目录运行：

```text
python -B skills/durable-task/scripts/test_memory.py
python -B skills/durable-task/scripts/test_reliability.py
```

自动检查配置在 [tests.yml](../.github/workflows/tests.yml)，使用 Python 3.12，在 Linux 与 Windows 运行相同命令。实际结果以对应提交的 Actions 记录为准。其他解释器版本和宿主尚未覆盖。

这些检查覆盖脚本输入、文件绑定、恢复包、迁移、预算记录和计时器边界。它们没有验证：

- 模型能否在上下文压缩后正确恢复或完成长任务；
- 任一数学、研究或代码结论的语义正确性；
- Qoder Cloud 的保活时长、回收时间、后台事件投递或成功率；
- Qoder CN CLI 的兼容性；

Cloud v0.2.2 为文档修订，没有进行新的 Qoder Cloud 实战复测。文档说明的流程不可当作平台保证。`UPLOAD.md` 是人工上传指引，ZIP 生成或本地校验也不表示附件已经交付。

## 2026.10.17.3 文档修订检查

通用 I010 与 Cloud v0.2.2 通过技能格式与相对链接检查。全部 9 个 Python 文件与上一发布逐字节相同；本次未在本机重复运行脚本套件，提交的自动检查结果见 Actions。

用 GPT-6 Luna 在独立上下文中做了两个合成情景、共三次短演练，提供技能入口和原始项目材料，不提供预期处理方法：

- 阅读页面迭代沿用一个状态文件，保存偏好和回退理由，修改页面后注明未做浏览器视觉检查，未建立账本。
- 研究依据撤回：首次识别旧结论失效，但只写新说明，原入口和报告未同步。补明更新原入口及受影响报告后，用新上下文从原始材料再试；报告已纠正，原状态仍保留旧 accepted 条目及撤回注记，未完全同步。

这些演练用于发现措辞遗漏。它们没有重现用户的原视觉任务、真实压缩或 Cloud 环境，也不能比较模型强弱、估算成功率或证明长期恢复可靠。入口同步仍需在实际使用中检查。

## 2026.10.18 合集发布

新增 progressive-reading、novel-worldbook、palimpsest，通用技能合入 I011 的两处文档说明。原有 9 个 Python 文件与上一发布逐字节相同；阅读分段器与提供的适配源逻辑相同，测试夹具读取明确指定 UTF-8。

本机新增运行阅读分段器 6 项测试并通过，覆盖连续还原、初始未读状态、非法尺寸、Unicode/CRLF/BOM 字节保留、关闭预览后的标题保密、空白及非法编码拒绝。可在仓库根复验：

```text
python -B -m unittest discover -s skills/progressive-reading/tests -v
```

CI 在 Linux 和 Windows 上运行全部四套检查，每个平台合计 60 项。具体运行结果以本发布提交对应的 Actions 记录为准。五个技能入口通过格式检查，相对引用、前置目录、来源差异和发布排除项已检查。

本次没有重新运行小说长时阅读、真实上下文压缩、Qoder Cloud 或数学证明器实验。来源维护记录中的小型续读演练属于既有记录，不计为本次新实验。palimpsest 的数学工作流经公开化文本审阅；格式与链接检查不证明其研究能力。

合集与单项 ZIP 保留相应 LICENSE 和版本信息，打包后检查成员字节与 CRC。novel-worldbook 单项包需要另外安装两个前置技能；合集包含所需目录。

## 2026.10.22 七技能修订

本次在 Windows、Python 3.12 运行原有四组共 60 项检查，以及 BoundForge 的 22 项测试，均通过。原有 Python 脚本与测试逐字节保持不变；BoundForge 仅统一文本换行、清理一处空行的行尾空格，所有 Python 文件与来源的语法树一致，其余运行资源字节一致。

新增运行方式：

```text
python -B scripts/validate_collection.py
```

这个检查覆盖七个包的入口名称、说明、NOTICE、HELP、许可证及本地 Markdown 链接。各技能还通过 skill-creator 的入口格式检查。公开文件检查排除本机路径、个人标识、凭据、私人记录与运行数据库；每个单项包附 MIT 许可。打包时逐成员比较字节并检查 ZIP CRC，解压后的合集运行同一套 82 项检查；BoundForge 单项 ZIP 解压后也运行了快速示例。

BoundForge 的测试与示例，从其安装目录运行：

```text
python -B -m unittest discover -s tests -v
python -B examples/quickstart.py
python -B examples/simulate_stagnation.py
```

快速示例记录 `inf_{x>0}(2+1/x)=2`，并给出不达到的论证。停滞示例使用合成时钟，没有运行数小时研究。CI 已加入 BoundForge 测试、快速示例及合集检查，在 Linux 与 Windows 执行；本提交的执行结果以 Actions 为准。

改写由主代理与三个 GPT 6 Luna 子代理完成，主代理检查集成。阅读、恢复和数学工作流做了文字情境核查；一次独立前向演练实际使用 BoundForge 研究 `inf_{x>0}(x+1/x)`，保存上下界、达到性论证及 SQLite 账本。主代理读回论证与最终状态，核对下界 2、上界 2、在 x=1 达到、无未关闭 work 或 episode、账本链与 SQLite 完整性通过。初次调用遗漏必填参数与误用示例 ID 后，按现有命令帮助修正即可继续；失败调用未写入记录。

这些是脚本检查、文档核查和一个小型实际用例；没有进行真实长时数学研究、小说全文阅读、上下文压缩恢复、Qoder Cloud 或证明器实验，不能据此估算研究成功率。
