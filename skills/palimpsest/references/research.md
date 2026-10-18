# 设计依据与适用边界

本文件用于解释/维护技能，不是每次解题必读的背景。核验日期：2026-10-06。以下区分论文/作者的报告、历史本地记录与本技能的设计选择；未把来源结论写成所有模型、领域的普遍定律。arXiv 预印本不自动代表同行评审认可。

## 数学目的

**Terence Tao, Mathematics in the age of AI (2026)，§5–8。**
[正文 v1](https://arxiv.org/html/2608.16753v1)，[摘要与版本](https://arxiv.org/abs/2608.16753)。
Tao 在假定 AI 研究能力会进步的条件下讨论数学的价值。他将解题的目标扩展为核查、解释、社群吸收和进入持久理论，并指出这些目标不能由单一产量代理。本文是数学实践的观点/分析，不是调度算法消融。
**采用的设计**：交付核心机制、困难步骤与假设边界；不将长度/接受数等同贡献；可解释与复用是工作目的，社群接受则是外部过程，技能不能自授。

**William P. Thurston, On proof and progress in mathematics (1994)。**
[作者论文](https://arxiv.org/abs/math/9404236)。本次核验摘要，详细章节未作为新操作规则的证据。
论文讨论形式定理证明之外的数学进展。**采用的设计**：保留原技能重视理解和失败路线的方向；不把“僵局是唯一价值来源”保留为定律，不声称日志必然能训练审美。

**Leslie Lamport, How to Write a Proof (1993)。**
[作者说明页](https://lamport.azurewebsites.net/proofs/proofs.html)，[Microsoft Research 原文](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/12/How-to-Write-a-Proof.pdf)。本次读取作者说明页。
层次化证明有助于明确推理结构。**采用的设计**：困难的长证明按需层次化；不固定深度/节点配额，不用 linter 代替逻辑验证。

## 研究代理与形式化

**Tony Feng et al., Towards Autonomous Mathematics Research (Aletheia, 2026)，§2、§3、§6。**
[正文 v3](https://arxiv.org/html/2602.10177v3)。
作者报告自然语言 Generator–Verifier–Reviser 系统，结合工具与文献检索；结果的新颖性、重要性和自主程度分开评价，且说明文献复查会降低新颖性判断。
**采用的设计**：允许有具体推理内容的审查与修订；引用要查原文；分别描述正确性、原创性与参与方式。该系统的自然语言验证并非 kernel 认证，也不证明三角色或其超参数普遍最优。

**Haocheng Ju et al., Automated Conjecture Resolution with Formal Verification (Rethlas/Archon, 2026)，§3、§4.4、§5、附录16。**
[正文 v2](https://arxiv.org/html/2604.03789v2)，[作者 Archon 仓库](https://github.com/frenzymath/Archon)。
作者将带定理检索的非形式研究与结构化形式化衔接；Archon 能补非平凡缺口。附录16把完整构建与短 specification 的 Comparator 比对作为不同检查，短 specification 的语义仍需审查。
**采用的设计**：按引理依赖拆分工作；形式化补出的数学内容需回写；正式目标与原题单独核对。技能不自动部署这两个系统，也不依赖其服务。

**Lushi Pu et al., MathForm: Scaling Mathematical Autoformalization with Knowledge Retrieval and Verification-Guided Refinement (2026)，§3、§4.1.3、附录D。**
[正文 v1](https://arxiv.org/html/2608.14221v1)。
作者区分 Syntax Check 和 Consistency Check，使用库检索和验证反馈改进 statement autoformalization。其语义一致性评估使用 LLM judge，不能据此当成语义等价的机器证明。
**采用的设计**：编译通过与忠实翻译必须分别核查；模型语义审查只是明确的证据种类，不能冠以机械认证。该论文针对训练数据/特定模型，不推导出本技能的成功率。

**Mohammed Abouzaid et al., First Proof Second Batch (2026)，方法及 Refereeing/Editorial Decisions。**
[正文 v1](https://arxiv.org/html/2606.18119v1)，[项目](https://1stproof.org/)。
作者用来自真实研究、评测前未公开的题目，发布尝试、审稿意见与决策依据。
**采用的设计**：行为测试看真实数学结果，保留未通过项与具体理由；同模型审查不声称等价于专家审稿，不根据几个小测试外推研究能力。

## 多样性与反馈

**Albert Q. Jiang et al., Draft, Sketch, and Prove (2022/ICLR 2023)，§5、§6/Figure 5。**
[正文](https://arxiv.org/html/2210.12283)。
其特定 miniF2F 实验在固定 autoformalization 尝试数下，多份 informal draft 优于反复形式化同一 draft。
**采用的设计**：保留实质不同路线，避免原路空转。此结果不证明“多样性比深度普遍重要一个数量级”，也不支持按难度开 8–20 个代理。

**Kefan Dong, Tengyu Ma, STP: Self-play LLM Theorem Provers with Iterative Conjecturing and Proving (2025)。**
[原论文摘要与版本](https://arxiv.org/abs/2502.00212)。本次核验摘要，未沿用旧稿中的未重新查证消融数字。
STP 是围绕可检查形式猜想/证明的训练机制，包含 barely-provable 的猜想选择。**采用的设计**：命题变体可成为研究旁支；不把训练系统的采样/配额/模型更新规律照搬到一次 inference 工作流。

**Jie Huang et al., Large Language Models Cannot Self-Correct Reasoning Yet (2023/ICLR 2024)，§3、§4、§6。**
[正文](https://arxiv.org/html/2310.01798)。
作者在所测模型/任务中观察到无外部反馈自纠的局限，并将辩论与等调用量 self-consistency 比较。
**采用的设计**：不把赞同/评分当证明，不以重复复查升级验收；反馈应具体。该研究不证明“任何同模型逻辑审查都信息量为零”，更不禁止推理修正或所有互评。新版允许可定位的逻辑反驳，即使来自内部审查。

## 形式证明的信任边界

**Lean Reference Manual，Axioms / Tactic Reference。**
[公理与传递依赖](https://lean-lang.org/doc/reference/latest/Axioms/)，[sorry/admit](https://lean-lang.org/doc/reference/latest/Tactic-Proofs/Tactic-Reference)。读取日期：2026-10-06；latest 是动态版本，执行时按实际工具链核对。
官方文档说明 `#print axioms` 可检查传递公理依赖；`sorryAx` 不能出现在完成证明的依赖中，标准公理与原生计算的编译器信任边界需区分。
**采用的设计**：完整构建、目标语义、公理审计、依赖版本分别记录；失败不否证原数学陈述；原生计算不伪称仅内核信任。

## 实践中的设计动机

以下失效模式用于解释技能约束：有限样本被升级成一般结论；局部证书被当作完整目标认证；条件结果与未证桥梁被单一状态遮蔽；非法反例、证据撤回或代码版本变化未传播到下游。私人案例与材料未随包分发，这些说明不构成对旧项目结果的公开复核。

已有 durable-task 时复用其恢复入口与验证协议；按任务需要选择记录粒度，不为每个数学问题创建数据库。

## 明确舍弃的旧推断

“无外部锚信息量恒零”“固定 L0>L1>L2>L3>L4”“自评四问能测 range”“通用 verifier 算力比/误差率”“一次无反例就数学收敛”“三守卫必为硬锚”均不保留为科学定律。外部锚更可复现，但有输入、适用域和实现的信任边界；数学理解与严谨逻辑也有用，不能由机械标签统一替代。
