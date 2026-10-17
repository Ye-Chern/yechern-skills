# 便携账本操作

Python 仅用标准库；不安装依赖。以下 `<skill>` 是本轮实际解压的技能目录，`<project>` 是任务根。账本建议为 `<project>/memory`，必须在项目内。当前状态唯一来源是追加事件 SQLite；CONTRACT.md 保留用户约束；CAPSULE/RECOVERY_INDEX/FOCUS/导出为再生视图。

## 新建

先写 `<project>/contract.md`，再执行：

```text
python3 <skill>/scripts/task_memory.py init --root <project>/memory --project <project> --contract <project>/contract.md
```

节点 JSON 最小可用例子（路径相对 project；替换为本任务实际观察）：

```json
{
  "id": "E1", "kind": "evidence", "title": "本次独立重放结果",
  "status": "accepted", "scope": "只覆盖 inputs/case.json 中的实例",
  "rationale": "供 C1 的有限实例判断使用",
  "depends_on": [], "files": ["results/check.txt", "code/check.py", "inputs/case.json"],
  "validation": {
    "method": "实际运行独立重放器，核对计数与不变量",
    "result": "填本次真实结果；未运行不得 accepted",
    "limits": "实例验证不证明所有输入"
  }
}
```

```text
python3 <skill>/scripts/task_memory.py put --root <project>/memory --file <project>/node.json
python3 <skill>/scripts/task_memory.py show --root <project>/memory --id E1
```

kind 为 evidence/claim/decision/task。前三者 status 为 draft/accepted/retracted/superseded；task 为 open/done。accepted evidence 须有本地原始来源/结果文件和 validation.method/result/limits；accepted claim 须依赖 evidence/claim 并有验证范围。accepted 仅指记录的 scope，不保证理论真实。关键 claim 可补 `claim_type`、`completeness` 等字段，工具保存但不会自行验证它们。

更新先 show 最新版本，再提交**完整输入节点**，`files` 仍为路径字符串，不复制输出里的哈希对象、revision、dep_revisions：

```text
python3 <skill>/scripts/task_memory.py put --root <project>/memory --file <project>/updated-node.json --expected-revision 1
```

依赖只列成立所必需的前提；撤回的旧节点在 rationale 中当历史指针，不能作为当前 depends_on。文件和依赖版本变化会使后代 needs-review；重验上游后，旧下游仍须自己复核。revision 防止旧 JSON 覆盖新记录；它不检查验证描述的真实性。

## 前沿与恢复

focus JSON 示例：

```json
{
  "ids": ["T1"], "next_action": "验证下一块的覆盖完整性，保存校验输出",
  "open_questions": ["剩余区间是否已完整覆盖？"],
  "do_not_repeat": ["截断搜索的零命中不能推出不存在"],
  "waiting_on": ["J1: jobs/J1.json; last committed 4; process status unknown; next verify block 5"]
}
```

```text
python3 <skill>/scripts/task_memory.py focus --root <project>/memory --file <project>/focus.json
python3 <skill>/scripts/task_memory.py resume --root <project>/memory
python3 <skill>/scripts/task_memory.py audit --root <project>/memory
```

focus 先提交事件再生成视图；输出 `Focus COMMITTED; views pending` 时状态已保存，不重复提交，修复原因后 resume。默认恢复入口预算 2400 Unicode 字符（不是 token）。入口最多列 8 个依赖 ID；完整状态在 RECOVERY_INDEX.md、全部前沿字段在 FOCUS.json，完整节点用 show。路由提示出现时必须实际读相关文件；遗漏字段不会被当成已读。极小预算仍可能报错，按给出的 `--chars` 重试。

audit 的 0 表示字节/已声明边未检测到漂移；2 表示需复核；1 表示输入/工具失败。`review_order` 仅给复核拓扑顺序，不执行命令、不验数学语义，不自动刷新记录。不拿“audit 0”当任务完成条件。

接受新结论后，检查它实际解除了哪些 task/前沿阻断，按最新证据更新这些节点和 focus。交付前读当前 CAPSULE 与最新结论对照；旧 next_action/open_questions 不会因 `resume` 或 pack 自动变成正确状态。根目录 focus.json 是 focus 命令的输入草稿，账本 FOCUS.json 是当前再生视图：有旧草稿时注明非当前入口或同步它，不能让恢复者猜选哪份。报告只需定向检查受新结论影响的段落，撤回的历史有标记地保留，不能在“当前障碍”中继续引用已解除的问题。

## 迁移旧 durable-task

完整复制旧项目并保留 `files` 所需目录布局：

```text
python3 <skill>/scripts/task_memory.py relocate --root <new-project>/原账本相对路径 --project <new-project>
python3 <skill>/scripts/task_memory.py resume --root <new-project>/原账本相对路径
```

本版拒绝直接读取旧绝对根账本，防止副本误读原件。relocate 校验当前非 retracted/superseded 节点的绑定文件后，追加相对布局；不改证据哈希，不写旧项目。退休节点保留旧哈希/历史，仍不可当当前证据，不因迁移复活。缺文件/不同内容即拒绝，先找正确完整输入；不能伪造匹配。旧包保留，不原地转换唯一原件。

Windows/云端之间须逐字节复制，不能用 read_text/write_text 重新保存证据。哈希不同先分清换行、编码、序列化与语义变化；CRLF 与 LF 可能解释差异，但不得静默规范化来通过审计。只试了几种序列化不能断言原字节不存在。找到真正匹配旧哈希的候选也仍须核对来源和语义；需要向前重验时按新版本记录实际验证。

旧包可能漏掉绑定过的二进制，也可能只保留日志。不能用重新编译的不同字节替换旧哈希并称原包完整。如果找不到完整输入，保留旧账本，在独立入口记录哪些主张只是“原作者曾声明”，读取可用日志/源码继续不依赖缺失项的工作；需要重新验收时创建本次证据。不要让一个缺失的旧证据阻止所有独立分支，也不能静默把原 accepted 转成新的验收。

若原 ZIP 少了一层 `work/` 而节点路径仍是 `work/code.py`，在隔离项目中重建原布局再 relocate，记录这次搬运；不能仅缩短数据库路径来让检查通过。修改包装脚本前确认根从当前目录派生，彩排不得含指向真实库的绝对写路径。

## 恢复包

暂停写入，输出必须在项目之外且为新文件：

```text
python3 <skill>/scripts/cloud_bundle.py pack --project <project> --ledger <project>/memory --output <outputs>/recovery-001.zip
python3 <skill>/scripts/cloud_bundle.py verify --zip <outputs>/recovery-001.zip
python3 <skill>/scripts/cloud_bundle.py unpack --zip <inputs>/recovery-001.zip --target <new-empty-path>
```

pack 在私有副本用 SQLite backup 取一致快照，重建恢复视图与 EVENTS.jsonl，校验复制后的项目并记录 cursor。按全项目打包，略过 Python 缓存和 SQLite journal；不会自动精简历史证据。`--allow-review` 只允许明确未完成的恢复包，manifest 记录复核 ID。unpack 先逐项检查清单/哈希再发布到新目录，不覆盖现有项目。生成和 verify 均不代表已上传到 Qoder。

打包时暂停所有写者；工具能检测部分并发变化，但不是全文件系统事务。大量无关备份应先按本任务契约整理，保留历史所需证据。bundle 清单证明包内字节，不证明来源可信或语义正确；无法 Python 执行时用手工等价入口与逐项文件清单，明确未自动校验的范围。
