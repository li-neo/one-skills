# Candidate Output

候选 Skill 位于：

[`../../examples/mao-methods/skill/mao-methods/SKILL.md`](../../examples/mao-methods/skill/mao-methods/SKILL.md)

当前 Pack 保持 `verify: blocked`，原因不是结构或来源失败，而是 one-skills 要求 V2 预测力和最终行为结果由独立 Answer Agent 或人工评审提供。

已确定完成：

- Source Catalog 集合质量门通过；
- 4 个结构化 Claim 在多个语境复现，并有独立 provenance group；
- 候选 Skill 通过静态结构、链接和 canonical/runtime 一致性检查；
- `evaluation_only` holdout 未进入构建语料。

尚未声称完成：

- canonical 行为题的独立执行；
- holdout 的盲测；
- 与 GitHub 对照 Skills 的同题 paired 比较；
- release / install / Darwin evolve。
