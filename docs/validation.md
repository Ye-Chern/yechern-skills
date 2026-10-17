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

Cloud v0.2.1 的文档在测试记录之后有修订；修订后没有进行新的 Qoder Cloud 实战复测。文档说明的流程不可当作平台保证。`UPLOAD.md` 是人工上传指引，ZIP 生成或本地校验也不表示附件已经交付。
