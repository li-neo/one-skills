# 毛泽东著作方法 Skill

这是 one-skills 的真实蒸馏案例：从公开著作中提取调查、矛盾分析、反馈和阶段方法，同时把版本问题、历史失败、基本权利与独立反证写入运行门。

## 产物

- [v0.4 核心布局中的双层 Runtime Skill](../../packs/mao-methods/skills/mao-methods/SKILL.md)
- [能力图谱与学习入口](../../packs/mao-methods/INDEX.md)
- [Object Overview](../../packs/mao-methods/OBJECT_OVERVIEW.md)
- [Capability Portfolio](../../packs/mao-methods/VERIFIED_PORTFOLIO.md)
- [Digest](../../packs/mao-methods/DIGEST.md)
- [高质量来源目录](SOURCE_CATALOG.json)
- [GitHub 社区对比](COMMUNITY_COMPARISON.md)
- [Builder 能力规格](CAPABILITY_SPEC.json)
- `evals/`：隔离 Answer/Judge 的候选 V2/V3 记录
- `sources/`：构建语料的短引、转述和边界记录
- `sources/99-holdout-public-health.md`：不进入构建语料的独立评测材料

`skill/mao-methods/` 保留为 v0.2 单入口候选，用于回归和架构差异审计，不再是
当前发布产物。

## 与人格模拟的区别

本 Skill 不扮演毛泽东，不称用户为“同志”，不生成“毛泽东会怎么看”的确定答案。它只运行可追溯的方法结构，并把现代使用明确标为框架迁移。

## 来源质量结果

```text
候选来源：8
进入构建：7
隔离 holdout：1
独立来源组：4
一手来源：4
研究问题覆盖率：100%
```

运行：

```bash
python3 scripts/one.py source audit \
  --catalog examples/mao-methods/SOURCE_CATALOG.json \
  --type methodology \
  --mode deep

python3 scripts/one.py validate \
  examples/mao-methods/skill/mao-methods
```

## 状态

v0.4 Pack 已发布，包含 1 个显式入口和 12 个内部节点：3 个 verified core、
7 个 supporting principles、2 个 governance gates。三条件盲测使用
`model-shared/session-separated` 隔离会话，60/60 通过；综合分 `99.7950`，
较冻结 Cangjie 基线 `77.0797` 领先 `22.7153`。全部安全、引用、反触发、
sibling、Hash 和 holdout 隔离硬门通过。权威结果见
`packs/mao-methods/evaluations/comparison-report.json`。

v0.4 仅合并生命周期、Recipe、保护约束与来源质量真源；Runtime Skill、60 题评测
和冻结 Skill Hash 保持不变。核心质量门结果为可靠性、完整性、准确率均 `1.0`。
