# 学习路径与经验进化

## 学习路径

每个新 Pack 在 Ingest 后生成 `LEARNING_PATH.json`：

- 编译前按原来源结构保留学习顺序；
- 编译后优先使用 Capability 的 `depends_on` 关系；
- 每个节点记录目标、先修节点、来源定位和掌握检查。

```bash
one learn path <pack>
one learn init <pack> --learner alice
one learn next <pack> --learner alice
one learn record <pack> \
  --learner alice \
  --node <node-id> \
  --score 0.9 \
  --evidence "能脱稿解释、应用并说出边界"
one learn status <pack> --learner alice
```

得分达到 `0.8` 时进入 mastered，并按 `1/3/7/14/30` 天安排复习。学习者状态是独立派生物，不修改来源、Claim 或 Skill。

## Skill 召回

```bash
one skill-search "只看行业报告，尚未访谈用户" \
  --root ./packs/example/skills \
  --root ~/.claude/skills
```

召回分开计算：

- name
- description
- triggers
- anti_triggers
- procedure
- body

结果输出每字段 sparse/dense 分、总分、top-two margin 以及 `selected/confirm/abstain`。召回只是第一阶段；是否加载和任务是否成功必须另行评测。

## 部署经验

```bash
one experience record <pack> \
  --skill example-skill \
  --task-signature "把相关性误当因果" \
  --outcome corrected \
  --result-summary "回答遗漏替代解释" \
  --correction "先列替代解释，再找干预证据" \
  --evidence-locator run:2026-08-06-001

one experience mine <pack> --minimum-occurrences 2
one experience status <pack>
```

硬约束：

- 事件 append-only；
- `training` 与 `evaluation` 分离；
- 至少两次复现且 evidence locator 不同才形成候选；
- holdout 事件不参与候选挖掘；
- 候选不会自动改 Skill；
- 晋升仍需冻结 eval、before/after、独立结果和人工 keep/revert。

## 适用边界

当前学习状态是透明的规则系统，不是经过真实学生数据训练的 Knowledge Tracing 模型。当前经验挖掘按显式 task signature 聚合，不执行无监督语义聚类。两者都优先可审计和防泄漏，后续只有在真实 benchmark 上证明收益后才增加复杂度。
