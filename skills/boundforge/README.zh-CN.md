# BoundForge v2.1-alpha

一个本地数学研究记录与决策工具，用于持续探索、比较方向和恢复工作。

内循环帮助判断是否继续当前 episode、换方法或转向；外循环比较各方向的多个 episode。`inner_effort` 和 `outer_effort`（0—100）调节两层努力偏好，操作次数与工作时长由实际研究决定。

## 开始研究

需要 Python 3.10+，使用标准库。在本目录运行：

```bash
python examples/quickstart.py
```

自己的任务按常用路径进行：

1. 初始化问题与两个努力值，添加方向并开始 episode。
2. 用 `work-start`、`work-end` 记录研究时间。随手提交有用观察、方法、障碍和负面结果；这些探索条目可省略附件。
3. 下界、上界和引理等主张附论证材料，实际自查后记录 `self_check`；需要其他核查方式时再选用。
4. 用 `state` 恢复材料与进展，用 `decide` 辅助判断下一步。根据数学结果和新想法继续、换方法或转向。
5. 临时暂停时结束 work，保留可继续的任务；最终完成时 `finalize`。

模型可靠性表是可选扩展；提供时用 `--model-index` 选模型行。可用 `conjecture`、`evidence` 记录候选和线索，`candidates` 查看优先级。

命令选项：`python -m boundforge --help`。研究流程见 [SKILL.md](SKILL.md)，常用数据与状态含义见[账本说明](references/ledger.md)。

## 按需查看

- 遇到异常、失效依赖、意外中断或其他少见操作：[HELP.md](HELP.md)。
- 项目统一的能力边界与通用免责：[NOTICE.md](NOTICE.md)。
