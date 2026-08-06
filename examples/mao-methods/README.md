# 毛泽东著作方法 Skill

这是 one-skills 的真实蒸馏案例：从公开著作中提取调查、矛盾分析、反馈和阶段方法，同时把版本问题、历史失败、基本权利与独立反证写入运行门。

## 产物

- [候选 Skill](skill/mao-methods/SKILL.md)
- [高质量来源目录](SOURCE_CATALOG.json)
- [GitHub 社区对比](COMMUNITY_COMPARISON.md)
- `sources/`：构建语料的短引、转述和边界记录
- `sources/99-holdout-public-health.md`：不进入构建语料的独立评测材料

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

`candidate`。静态结构、来源质量和测试 Schema 可以确定性验证；独立 Answer Agent 尚未运行 canonical 与 holdout，不能标记为 released。
