# one-skills v0.3 完整蒸馏架构与毛泽东基准计划

## 一、Summary

本轮不再追加零散功能，而是修复 one-skills 从“证据基础设施”到“高质量能力成品”之间的断层。

目标：

1. 保留 one-skills 已有的 Source Catalog、证据账本、版本、ACL、检索、状态机和发布硬门。
2. 把 Cangjie 真正有效的 `整体理解 → 多视角候选池 → 三重验证 → 原子能力 → 关系图 → 学习路线 → DIGEST` 做成可运行代码，而不是文档承诺。
3. 吸收 Trace2Skill、SkillLens、SKILL-KD、Skill-Alpha、SkillHone 和 ContinualSkillBench 的行为评测、轨迹对比、结构化补丁、合并去漂移和回滚思想。
4. 七类 Profile 均拥有专属的理解、提取、编译和评测策略。
5. 重新蒸馏毛泽东方法 Pack，采用“一个显式总入口 + 8–12 个内部原子能力模块”的双层网络。
6. 使用相同 Answer Agent 对 `no-skill / Cangjie baseline / one-skills` 做 60 题盲测；只有综合分和硬门同时胜出才发布。

本轮明确不做：

- 不训练 Skill-Alpha 的 GRPO 模型；只吸收可审计的结构化编辑与 rollback reward 协议。
- 不引入图数据库；继续使用 SQLite/PostgreSQL 的 typed nodes + lineage edges。
- 不把 GitHub Star、静态关键词分或 LLM 自评分当作任务效果。
- 不把非正式“第 6–9 卷”作为受保护 Claim 的证据。
- 不做毛泽东第一人称人格模拟，不把敌我、清洗、运动或战争动作商品化为现代组织工具。

## 二、已锁定决策

### 2.1 产品决策

- 交付形态：双层能力网络。
  - 对 Runtime 只暴露一个 `mao-methods` 显式入口。
  - 内部保留 8–12 个可独立阅读、学习、测试和引用的原子模块。
  - 内部模块默认不参与全局自动 Skill 召回，避免 shadowing。
- 来源：官方一手公开文本 + 官方历史反证 + 独立学术研究。
- 架构推进：垂直切片，每完成一个主链阶段就用毛泽东案例验收，再扩展到七类 Profile。
- 人工确认：
  1. Object Overview 确认；
  2. Verified Capability Portfolio 确认；
  3. 发布仍需最终批准。
- 开源对照：只对比 Cangjie 系产物 `chinapathbreaker/mao-skill@0c127bd`。

### 2.2 模型角色

提供三套配置时使用独立 Builder、Answer Agent、Judge；只有一套配置时：

- 仍创建三个隔离会话；
- 不共享 prompt、轨迹和预期答案；
- 报告标记 `isolation_level=model-shared/session-separated`；
- 不宣称达到多模型独立性。

角色配置新增：

```text
ONE_SKILLS_BUILDER_BASE_URL / API_KEY / MODEL
ONE_SKILLS_ANSWER_BASE_URL  / API_KEY / MODEL
ONE_SKILLS_JUDGE_BASE_URL   / API_KEY / MODEL
```

兼容回退：

```text
ONE_SKILLS_MODEL_BASE_URL / API_KEY / MODEL
```

密钥只从环境读取，不写 Pack、日志、Git 或测试报告。

### 2.3 胜出标准

综合分权重：

| 维度 | 权重 |
|---|---:|
| 真实任务效果 | 50 |
| 触发、拒答与模块路由 | 15 |
| 证据与引用 | 10 |
| 安全与现代迁移边界 | 15 |
| 知识组织与学习 | 5 |
| 成本与延迟 | 5 |

胜出条件：

- one-skills 总分至少比 Cangjie baseline 高 5 分；
- 真实任务效果不得低于 Cangjie；
- 以下硬门不可被加权分补偿：
  - safety 用例 100%；
  - 引用定位可解析率 100%，引用支持率至少 95%；
  - should-not-trigger 和 sibling hard gate 100%；
  - Agent Skills / Pack 静态验证 0 errors；
  - holdout 不得进入 Builder 输入；
  - Answer Agent 完整输出、Judge 判定、模型身份和内容哈希全部可回放。

## 三、Current State Analysis

### 3.1 可保留的基础

- `src/one_skills/pipeline.py`：十阶段状态、Source Version、失效与恢复。
- `src/one_skills/source_quality.py`：来源集合质量门、独立组、角色和 holdout。
- `src/one_skills/database.py`：Source → Document → Chunk → Claim → Capability → Skill 血缘。
- `src/one_skills/skill_retrieval.py`：字段感知 sparse/dense 召回、margin 与 abstain。
- `src/one_skills/learning.py`：学习者状态和间隔复习。
- `src/one_skills/experience.py`：append-only 部署反馈。
- `src/one_skills/validation.py` / `delivery.py`：冻结测试和发布硬门。
- 当前 `bd8cb39` 已通过 Python 3.10/3.11/3.12 与 PostgreSQL/pgvector CI。

### 3.2 导致结果不如 Cangjie 的根因

1. `OBJECT_MAP.md` 由 `_write_object_map()` 生成，但维度全部是“待提取”，没有真正的整体理解。
2. `Profile.compiler="atomic-network"` 只是字符串；没有对应的 atomic-network 编译器。
3. `Candidate` 只有标题、摘要和 Evidence ID，无法表达：
   - 成立假设；
   - 机制；
   - 书中应用；
   - 触发与反触发；
   - 失败模式；
   - 与其他候选的重叠或冲突。
4. `extract_candidates_with_model()`：
   - 只截取前 50,000 字；
   - 没有 Object Overview 作为每个 extractor 的全局锚点；
   - 多视角输出直接按标题相似度合并；
   - 没有分块 map/reduce、候选聚类和冲突合并。
5. `capability_from_candidate()` 和 `compiler.py` 给所有候选套同一 Profile 通用步骤，丢失候选本身的方法结构。
6. `_build_index()` 只列 Skill 文件，并明确不生成关系；“原子网络”没有落地。
7. `LEARNING_PATH.json` 在编译前按章节标题生成；不是概念图，也不是能力先修图。
8. `default_tests()` 是通用占位句，不来自真实触发、兄弟模块、历史失败或任务结果。
9. `evaluation.py` 只聚合 `{id, passed}`，不保存完整回答、Judge 证据、Skill Hash、no-skill baseline 或成本。
10. 当前只有一个 Provider 配置，Builder、Answer、Judge 无法隔离。
11. Source Catalog 只能人工填写；没有本地、GitHub、Hugging Face 和外部发现结果的统一候选层。
12. Experience Ledger 只能形成文本候选，不能生成 `CREATE/UPDATE/MERGE/PRUNE/NOOP` 补丁，也没有 edit-level rollback comparison。
13. 当前毛泽东构建语料是 7 份短捕获笔记，只足以证明 4 个 Claim，不足以支撑“完整方法能力网络”。

### 3.3 外部架构采纳矩阵

| 来源 | 采纳 | 不照搬 |
|---|---|---|
| Cangjie RIA-TV++ | Object Overview、五视角候选池、RIA++、关系图、GLOSSARY、DIGEST、学习顺序 | 不采用非法 frontmatter，不采用静态 dry-run 自证 |
| Nuwa | 六维人物研究、时间变化、外部评价、未表态主题、Fidelity 角色隔离 | 不默认第一人称冒充 |
| neo-skills v0.2.8 | 统一 gate/control、source sync、Skill Hash、用户确认 Git ratchet | 不退回无数据库的单 Pack 实现 |
| Trace2Skill | 多轨迹并行诊断、层级合并、冲突消解、OOD 验证 | 不引入其领域绑定运行器 |
| SKILL-KD | student failure 与 teacher/success trajectory 的对比补丁、漂移感知合并 | 不让单次失败自动改 Skill |
| Skill-Alpha | `CREATE/UPDATE/MERGE/PRUNE/NOOP`、逐编辑 downstream rollback reward | 本轮不训练 GRPO |
| SkillLens | `with-skill - no-skill` 真实效果、跨 Builder/Target 评测 | 不使用自评结构分替代行为增益 |
| SkillHone | whole-folder edit、eval/skill 分离、持久决策历史 | 不要求本地 Forgejo 作为核心依赖 |
| ContinualSkillBench | 能力链、顺序任务、碎片化指标 | 不用任务数量增长冒充能力增长 |
| Field-Aware Retrieval / Skill Shadowing | 字段级召回、集合竞争测试、入口路由 | 不把内部模块全部暴露为自动 Skill |
| Hugging Face `claude-agent-skills-benchmark` | 参考 query/rubric/attachment 形态 | 不直接引入低样本且含来源/版权不清附件的数据 |

参考版本和论文 URL 写入 `docs/RESEARCH_2026_ARCHITECTURE_AUDIT.md`，包括：

- `kangarooking/cangjie-skill@149cb39`
- `li-neo/neo-skills@d88f6db`
- `alchaincyf/nuwa-skill@27642f5`
- `Qwen-Applications/Trace2Skill`
- `Tencent/SkillHone`
- `microsoft/SkillLens`
- `ejhshen/skill-alpha`
- arXiv `2607.28048`、`2603.25158`、`2608.01678`、`2608.03874`、`2608.02880`、`2605.24050`

## 四、目标架构

### 4.1 两个平面

**确定性控制平面**

- 状态机、权限、Source Hash、Schema、Lineage、测试冻结、发布、回滚。
- 不做语义判断。

**语义能力平面**

```text
Source Discovery
  -> Source-Set Quality Gate
  -> Object Overview
  -> Profile-specific Multi-view Extraction
  -> Candidate Consolidation
  -> V1/V2/V3 Verification
  -> Capability Portfolio
  -> Dual-layer Compile
  -> Capability Graph + Learning Path + DIGEST
  -> Blind Baseline Evaluation
  -> Structured Evolution Patch
```

### 4.2 十阶段状态机的新产物语义

保留现有十阶段名称，避免破坏 CLI 和 Pack 恢复语义：

| 阶段 | 必需产物 |
|---|---|
| contract | `DISTILLATION_CONTRACT.md`、研究问题、目标用户、成功指标 |
| ingest | Source Catalog、候选来源审计、捕获版本、holdout 隔离 |
| map | `OBJECT_OVERVIEW.json/md`、对象骨架、术语、张力、缺口；人工确认 1 |
| extract | Profile 专属候选池、案例池、反例池、术语池 |
| verify | V1/V2/V3 记录、合并/降级/拒绝理由、Capability Portfolio；人工确认 2 |
| compile | 总入口、内部原子模块、Capability IR、模块测试 |
| link | Capability Graph、INDEX、GLOSSARY、DIGEST、先修学习路径 |
| test | 三条件盲测、完整回答、Judge 结果、综合分、硬门 |
| ship | Model Card、质量/来源/对比报告、安装与导出 |
| evolve | 结构化补丁、before/after、回滚结论和用户 keep/revert |

`map` 阶段就必须产生可读产物；`verify` 阻塞不能再让 INDEX 为空。未验证节点标记 `candidate`，但不能安装。

### 4.3 核心 IR

新增或扩展以下结构：

**ObjectOverview**

- `thesis`
- `structure[]`
- `key_terms[]`
- `argument_or_mechanism_chain[]`
- `timeline_or_state_model[]`
- `tensions[]`
- `limitations[]`
- `research_gaps[]`
- `source_coverage`

**CandidateUnit**

- 身份：`id/title/type/profile/view`
- 内容：`problem/claim/assumptions/mechanism`
- 执行：`triggers/anti_triggers/inputs/procedure/branches/output/done`
- 约束：`failures/boundaries/counterexamples`
- 证据：`evidence_ids/source_contexts/independence_groups`
- 关系：`duplicates/contradicts/composes_with/depends_on`
- 验证：V1/V2/V3 分项记录、状态、降级去向、拒绝理由

**CapabilityPortfolio**

- 通过、降级、合并、拒绝四类候选；
- 覆盖矩阵：研究问题 × 能力；
- 原子性、重叠率和碎片化指标；
- 用户确认记录。

**CapabilityGraph**

- 节点：term、claim、case、counterexample、capability、governance gate；
- 边：supports、contradicts、depends_on、contrasts_with、composes_with、invalidates；
- 每条边必须有 Evidence ID 或明确标为 `derived/reviewed`。

**EvaluationRun**

- suite/source/skill/answer/judge hashes；
- role/model/isolation level；
- condition：no-skill / cangjie / one-skills；
- 完整 prompt、回答、判定证据、token/latency；
- 分维度分数、硬门、综合分。

## 五、七类 Profile 专属实现

将 `profiles.py` 的浅层 `Profile` 升级为 `ProfileSpec`，每个 Profile 必须定义 overview、extractor views、compiler、relation policy、learning policy 和 evaluation policy。

| Profile | 专属提取视角 | 编译目标 |
|---|---|---|
| person | writings、conversations、decisions、timeline、external_views、expression | perspective router + 3–7 心智模型 + 诚实边界 |
| content | framework、principle、case、counterexample、glossary | overview + 原子知识能力网络 + digest |
| methodology | assumptions、mechanism、branches、applications、failures | 方法入口 + 可执行原子模块 |
| sop | roles、preconditions、steps、exceptions、handoffs、verification | 状态化 workflow + 回滚/升级 |
| tool | operations、contracts、auth、side_effects、errors、readback | operation router + schema/tool helpers |
| skill | purpose、triggers、workflow、resources、tests、defects | whole-folder repair portfolio |
| hybrid | objects、permissions、knowledge、tools、orchestration、conflicts | 顶层 router + 子 Profile 能力 |

所有 Profile 共享 Evidence、Source、Capability Graph 和 EvaluationRun，但最终模板不能共享一套通用 procedure。

## 六、Proposed Changes

### 6.1 Schema 与模型

修改：

- `src/one_skills/models.py`
- `schemas/distillation-ir.schema.json`
- `schemas/pack.schema.json`
- `schemas/learning-path.schema.json`
- `schemas/protected-constraints.schema.json`

新增：

- `schemas/object-overview.schema.json`
- `schemas/candidate-unit.schema.json`
- `schemas/capability-portfolio.schema.json`
- `schemas/capability-graph.schema.json`
- `schemas/evaluation-run.schema.json`
- `schemas/source-candidates.schema.json`
- `schemas/evolution-patch.schema.json`

Pack 升级到 `schema_version: 0.3`。Validator 同时读取 0.2 和 0.3；0.2 只保持可读兼容，不能伪装拥有新语义产物。新增确定性迁移命令，只初始化缺失状态，不编造 Overview、关系或评测结果。

### 6.2 ProfileSpec 与整体理解

修改：

- `src/one_skills/profiles.py`
- `src/one_skills/recipes.py`

新增：

- `src/one_skills/overview.py`
- `src/one_skills/profile_specs.py`

实现：

- 按 Profile 生成 Object Overview；
- 长文本按自然章节 map，再由 Builder reduce；
- 每块都携带冻结 Overview 摘要和研究问题；
- map 输出必须逐字段引用来源；
- Object Overview 确认后冻结 Hash，后续 Source 更新使其 stale。

### 6.3 来源发现与准入

新增：

- `src/one_skills/source_discovery.py`

修改：

- `src/one_skills/source_quality.py`
- `schemas/source-catalog.schema.json`
- `src/one_skills/cli.py`

新增 CLI：

```text
one source discover --adapter local|github|huggingface|manifest ...
one source shortlist --candidates SOURCE_CANDIDATES.json ...
one source audit ...
```

Adapter：

- Local：目录、Glob、文件类型、Hash、许可旁证；
- GitHub：Repository/Commit/File identity、license、更新时间；
- Hugging Face：model/dataset card、license、gated 状态、revision；
- Manifest：接收外部 Web/Search Agent 的发现结果。

发现结果只进入 `SOURCE_CANDIDATES.json`，不能自动摄取。Shortlist 生成 Source Catalog 草案；质量门继续决定最终 ingest。

### 6.4 多视角提取、候选合并与验证

修改：

- `src/one_skills/extraction.py`
- `src/one_skills/provider.py`
- `src/one_skills/pipeline.py`

新增：

- `src/one_skills/portfolio.py`

实现：

1. 每个 Profile 按视角并发提取。
2. 对长语料逐块 map，保留所有来源定位。
3. 层级 reduce：
   - 同义候选合并；
   - 冲突候选并列；
   - case/counterexample/term 关联到 framework，不强制独立成 Skill；
   - 输出合并理由和损失检查。
4. V1：
   - 跨语境复现；
   - 独立来源单独记录；
   - 禁止同一材料多章节冒充独立来源。
5. V2：
   - Builder 生成来源未直接回答的新问题；
   - Answer Agent 只拿候选和证据回答；
   - Judge 判断是否产生非平庸、可证伪的新结论。
6. V3：
   - Judge 比较无 Skill baseline，判断是否只是常识；
   - 通用常识降级为 shared principle，不独立成模块。
7. 生成 `CANDIDATE_PORTFOLIO.md/json`、`VERIFIED_PORTFOLIO.md/json` 和逐候选 rejected 审计。

### 6.5 Profile 编译器与双层能力网络

重构：

- `src/one_skills/compiler.py`

新增：

- `src/one_skills/compilers/__init__.py`
- `src/one_skills/compilers/person.py`
- `src/one_skills/compilers/content.py`
- `src/one_skills/compilers/methodology.py`
- `src/one_skills/compilers/sop.py`
- `src/one_skills/compilers/tool.py`
- `src/one_skills/compilers/skill.py`
- `src/one_skills/compilers/hybrid.py`
- `src/one_skills/artifacts.py`

毛泽东方法 Pack 的目标布局：

```text
packs/mao-methods/
├── OBJECT_OVERVIEW.md
├── CANDIDATE_PORTFOLIO.md
├── VERIFIED_PORTFOLIO.md
├── CAPABILITY_GRAPH.json
├── INDEX.md
├── GLOSSARY.md
├── DIGEST.md
├── LEARNING_PATH.json
└── skills/mao-methods/
    ├── SKILL.md
    ├── capability.json
    ├── capabilities/
    │   └── <module>.json
    ├── references/modules/
    │   └── <module>.md
    ├── evals/canonical.json
    ├── evals/modules/
    │   └── <module>.json
    └── test-prompts.json
```

总入口负责：

- 显式激活；
- 事实契约；
- 选择 1 个主模块、最多 1 个辅助模块；
- 全局证据、版本、安全和权利门；
- 模块间状态传递。

内部模块负责：

- 一个明确问题；
- 精确 trigger/anti-trigger；
- 假设、步骤、分支、完成、判停、失败和 fallback；
- 书中应用、历史反例、现代迁移边界；
- Evidence IDs 和引用定位。

### 6.6 图谱、索引与学习

修改：

- `src/one_skills/database.py`
- `migrations/postgres/001_initial.sql`
- `src/one_skills/postgres.py`
- `src/one_skills/learning.py`
- `src/one_skills/retrieval.py`
- `src/one_skills/skill_retrieval.py`

新增：

- `src/one_skills/capability_graph.py`

实现：

- 复用 `lineage_edges`，增加 relation 白名单和 edge evidence metadata；
- SQLite/PostgreSQL 增加 `graph_edges` 或扩展现有边表以保存 status、confidence、evidence IDs；
- INDEX、GLOSSARY、DIGEST、LEARNING_PATH 全部由同一 Capability Graph 投影，避免四份文档漂移；
- 学习路径从 `depends_on` DAG 拓扑排序生成；
- 每个节点的 mastery check 直接来自模块 canonical tests；
- Retriever 采用两级路由：
  1. 先选顶层 Pack；
  2. 只在 Pack 内选模块。
- 顶层入口未显式命中时，内部模块不得参与全局召回。

### 6.7 三角色真实评测与 Cangjie 对比

修改：

- `src/one_skills/evaluation.py`
- `src/one_skills/delivery.py`
- `src/one_skills/validation.py`
- `src/one_skills/benchmark.py`
- `src/one_skills/provider.py`
- `src/one_skills/cli.py`

新增：

- `src/one_skills/model_roles.py`
- `src/one_skills/comparison.py`
- `benchmarks/mao-methods/suite.json`
- `benchmarks/mao-methods/baselines.json`
- `schemas/comparison-report.schema.json`

60 题固定构成：

| 类型 | 数量 |
|---|---:|
| 真实能力应用 | 18 |
| 模块路由与 sibling 混淆 | 12 |
| should-not-trigger | 10 |
| 安全与误用 | 8 |
| 引用、版本与归属 | 6 |
| holdout / OOD | 6 |

三条件使用相同 Answer Model、temperature、token budget：

1. no-skill；
2. Cangjie `chinapathbreaker/mao-skill@0c127bd`；
3. one-skills `mao-methods`。

执行规则：

- baseline 只按 frozen Commit 获取，不 Vendor 原始完整语料；
- 条件名称随机映射为 A/B/C；
- Answer Agent 看不到 rubric 和 expected；
- Judge 看不到项目名称和构建过程；
- 保存完整输出，不再只存 boolean；
- 报告给出任务成功率、路由混淆矩阵、引用支持、安全、上下文 token、延迟和综合分；
- Skill Hash、Source Set Hash、Suite Hash、Answer/Judge Model 写入结果；
- `release_pack()` 读取硬门与比较报告，不能靠手工改状态发布。

CLI：

```text
one model status
one evaluate run <pack> --suite ... --condition ...
one compare run <pack> --baseline ... --suite ...
one compare report <run>
```

### 6.8 持续进化与回滚

修改：

- `src/one_skills/experience.py`
- `src/one_skills/delivery.py`

新增：

- `src/one_skills/evolution.py`

实现结构化动作：

```text
CREATE / UPDATE / MERGE / PRUNE / NOOP
```

每个补丁必须包含：

- failure/success trajectory IDs；
- 修改目标：入口、模块、script、reference 或 test；
- 预期改善维度；
- 不可退化的 protected gates；
- before/after Skill Hash；
- training split rollback comparison；
- holdout 只用于最终晋升；
- 用户 keep/revert 决议。

至少两个独立复现事件才生成 patch proposal。单次失败只进入 history。

### 6.9 Guided Controller 与人工门

修改：

- `src/one_skills/guided.py`
- `schemas/session-state.schema.json`
- `docs/GUIDED_DISTILLATION.md`

保留 consent、权限和 evidence inventory 的确定性输入要求；语义内容只保留两次人工确认：

1. `map_confirm`；
2. `capability_confirm`。

`claim_review` 合并进 Capability Portfolio，避免 Overview、Claim、Capability 三次重复确认。发布确认保留。

### 6.10 文档、版本和 CLI

修改：

- `README.md`
- `SKILL.md`
- `docs/ARCHITECTURE.md`
- `docs/RESEARCH_2026_ARCHITECTURE_AUDIT.md`
- `docs/SOURCE_QUALITY.md`
- `docs/LEARNING_AND_EXPERIENCE.md`
- `docs/COMPLETION_AUDIT.md`
- `pyproject.toml`
- `src/one_skills/__init__.py`

版本升级到 `0.3.0`。文档必须区分：

- 已实现；
- 有单元测试；
- 有真实模型运行；
- 有基线胜出证据。

不再把“存在接口”写成“完整能力已落地”。

## 七、毛泽东垂直验收

### 7.1 重新建立研究问题

至少覆盖：

1. 调查如何改变先验判断；
2. 实践—认识—再实践如何形成反馈；
3. 多重矛盾如何阶段性排序和改判；
4. 一线经验如何汇总、返回和再验证；
5. 弱势条件下如何分阶段积累能力；
6. 中心任务与多目标协调；
7. 教条主义、信息失灵和坏消息受罚如何导致失败；
8. 版本变化、作者归属和现代推断如何区分；
9. 历史方法迁移到现代组织时的法律、权利和伦理边界。

### 7.2 来源集合

来源发现阶段优先：

- 官方公开《毛泽东选集》定稿文本；
- 官方《毛泽东文集》或经核验的相关公开著作；
- 中共中央党史和文献研究院版本研究；
- 1981 年历史决议；
- 独立学术研究，承担信息失灵、政策结果和反证角色；
- 单独的 evaluation-only 学术材料。

社区 Skill、非正式卷本和搜索摘要只能作为：

- 候选主题发现；
- baseline；
- 版本风险提示。

不能支持受保护 Claim。

仓库只保存允许的短引、结构化转述、定位和 Hash，不提交完整版权文本。

### 7.3 候选能力家族

提取时研究但不强制凑数：

- 调查与反先验；
- 实践—认识循环；
- 实事求是与反教条；
- 矛盾地图；
- 主要问题的阶段性改判；
- 一线反馈闭环；
- 坏消息通道与领导方法；
- 阶段识别与局部试点；
- 中心任务与资源协调；
- 复盘、自我纠错与版本纪律；
- 利益相关者协同的非敌我化迁移；
- 历史失效与权利治理门。

最终保留 8–12 个原子模块；证据不足、过度重叠、属于常识或不可安全迁移的候选必须降级或拒绝。

### 7.4 发布产物

- 完整 Object Overview；
- 按视角分组的候选池；
- Verified / Rejected Portfolio；
- 1 个显式总入口；
- 8–12 个内部模块；
- Claim/Case/Counterexample/Capability 图；
- INDEX、GLOSSARY、DIGEST；
- 能力先修学习路线；
- 60 题完整比较报告；
- Model Card、Source Quality、Provenance、Evolution readiness。

旧 `packs/mao-methods` 在 Git 历史中保留；新流水线通过后原路径重建，不复制一份不可维护的旧 Pack。

## 八、测试与验证

### 8.1 单元与集成测试

保留现有 27 项并新增独立测试文件：

- `tests/test_overview_and_portfolio.py`
- `tests/test_profile_compilers.py`
- `tests/test_source_discovery.py`
- `tests/test_capability_graph.py`
- `tests/test_role_separated_evaluation.py`
- `tests/test_evolution_patches.py`
- `tests/test_mao_pack_contract.py`

覆盖：

- 七类 Profile 各自生成不同 Overview、Candidate 和 Skill 结构；
- 长文分块后无章节遗漏，reduce 保留 Evidence；
- 同义候选合并、冲突候选并列、低价值候选降级；
- 顶层入口与内部模块的两级路由；
- 内部模块不能全局误触发；
- 关系边必须可追溯且先修图无环；
- learning path 与 capability graph 一致；
- Builder 无法读取 holdout；
- 三角色配置与单模型降级；
- Answer/Judge 结果绑定所有 Hash；
- 安全、引用和 sibling hard gate 不可补偿；
- patch rollback、NOOP 和用户 keep/revert；
- 0.2 Pack 可读、0.3 Pack 可完整验证。

### 8.2 无模型 CI

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests scripts
python -m ruff check src tests --select E,F,I --ignore E501
python scripts/one.py validate .
python scripts/one.py benchmark --suite benchmarks/profile-routing.json
git diff --check
```

GitHub Actions：

- Python 3.10 / 3.11 / 3.12；
- PostgreSQL 16 + pgvector；
- 所有外部 API 使用 fixture/mock，CI 不依赖密钥。

### 8.3 有模型验收

执行前检查：

```bash
one model status
```

然后：

```bash
one distill ... --source-catalog examples/mao-methods/SOURCE_CATALOG.json
one evaluate run packs/mao-methods --suite benchmarks/mao-methods/suite.json
one compare run packs/mao-methods \
  --baseline chinapathbreaker/mao-skill@0c127bd \
  --suite benchmarks/mao-methods/suite.json
one validate packs/mao-methods
one release packs/mao-methods
```

验收时人工核对：

- 60 题是否全部有原始 Answer/Judge 记录；
- 条件标签是否盲化；
- holdout 是否未出现在 Builder 请求；
- 引用是否逐条回到 Source/Chunk；
- 综合分是否领先至少 5 分；
- 所有硬门是否通过；
- `release` 是否由系统门而不是手工状态推进。

## 九、实施顺序

1. **冻结基线与补研究审计**
   - 冻结 one-skills `bd8cb39`、Cangjie baseline `0c127bd`、相关论文/仓库版本。
   - 写出旧架构可复现失败：空 Object Map、通用编译、占位测试、无行为 baseline。

2. **落地 v0.3 IR、ProfileSpec 和兼容读取**
   - Schema、dataclass、Profile contracts、0.2/0.3 validator。
   - 七类 Profile contract tests 先行。

3. **实现 Source Discovery 与真实 Object Overview**
   - 本地/GitHub/HF/manifest adapters。
   - 长文本 map/reduce、Overview Hash 和第一次人工门。
   - 立即用毛泽东来源集合验收。

4. **实现 Profile 多视角候选池和 Capability Portfolio**
   - 分块提取、层级合并、V1/V2/V3、降级/拒绝。
   - 生成第二次人工确认材料。
   - 用毛泽东候选覆盖率和重叠率验收。

5. **实现七类编译器和双层能力网络**
   - 先完成 methodology/content 垂直切片；
   - 再完成 person/sop/tool/skill/hybrid；
   - 生成 Graph、INDEX、GLOSSARY、DIGEST 和学习路径。

6. **实现三角色评测与 Cangjie 比较**
   - 冻结 60 题；
   - 跑 no-skill / Cangjie / one-skills；
   - 生成完整、可回放的综合报告。

7. **根据真实失败执行结构化进化**
   - 只对重复失败生成 patch；
   - 每次 edit 做 before/after；
   - 若不胜出则回滚，不降低测试门。

8. **发布与反向架构审计**
   - 毛泽东 Pack 通过所有硬门后发布；
   - 把案例暴露的缺口回写 ProfileSpec、Recipe 和测试；
   - 更新 Completion Audit，只记录实际证据；
   - 提交并推送 GitHub，等待全部 CI 通过。

## 十、风险与处理

| 风险 | 处理 |
|---|---|
| 单模型伪独立 | 报告隔离等级，不宣称多模型独立；保留未来三配置接口 |
| 8–12 模块再次 shadowing | 只有总入口参与全局召回，模块只在 Pack 内二阶段路由 |
| 内容覆盖和来源可信度冲突 | 非正式材料只做发现；核心 Claim 必须由正式来源支撑 |
| 多视角候选爆炸 | 分层 merge、重叠率、碎片化和 NOOP/PRUNE |
| Verify 阻塞导致无可读产物 | Overview、候选图和 portfolio 在发布前即可生成，明确 candidate 状态 |
| 测试泄漏 | Builder/Answer/Judge 文件和请求边界分离，holdout hash 只进 evaluator |
| LLM Judge 偏差 | 盲化标签、确定性硬门、保存证据；关键争议支持第二 Judge 或人工复核 |
| 进化越改越差 | edit-level rollback comparison、protected gates、用户 keep/revert |
| 成本失控 | 60 题固定预算、缓存按全 Hash 命中、失败先跑 routing/static 小门 |

## 十一、完成定义

本计划只有同时满足以下条件才算完成：

- 七类 Profile 都有专属可执行编译链和测试；
- 毛泽东 Pack 不是手写特例，而是由新流水线可复现生成；
- 产物完整度达到或超过 Cangjie：Overview、候选池、拒绝池、原子能力、关系图、学习路线、Glossary、Digest；
- 来源、Claim、关系、能力和回答都可追溯；
- 真实三条件评测完成，one-skills 综合分领先 Cangjie 至少 5 分；
- 所有不可补偿硬门通过；
- Pack 从 `verify: blocked` 经真实证据推进到 released；
- 全量本地测试和 GitHub CI 通过；
- 所有更改已提交并推送到 `origin/main`。
