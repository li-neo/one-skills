# 2026 蒸馏、Skill、检索与持续学习架构审计

审计日期：2026-08-06
目标：判断 one-skills 是否需要继续补强，并把有证据的改进落实到代码、Schema、测试和真实案例。

## 1. 结论

需要完善，但不需要推翻现有架构。

one-skills 已有统一 IR、十阶段状态机、证据账本、Profile、SQLite/PostgreSQL、混合召回、ACL、Recipe/Eval 冻结和 Guided Session。2026 年新证据暴露的主要缺口不是“有没有向量库”，而是：

1. 来源在进入 Pack 前没有集合级质量门；
2. Skill 被当普通长文档，缺少字段感知召回和拒答；
3. Content Pack 只有知识结构，没有显式学习依赖和学习者状态；
4. Darwin 只有候选评测，缺少部署反馈到候选规则的可恢复经验账本；
5. 中文候选门、增量证据失效和跨来源 Claim 复现存在具体实现缺陷；
6. 最新 neo-skills 的统一控制面、Guided 同步和 Git 决议棘轮仍有可吸收部分。

本轮形成的新主链：

```text
Intent Router
  -> Source Discovery Plan
  -> Source-Set Quality Gate + Evaluation Holdout
  -> Immutable Ingest
  -> Explicit Claim Families + Evidence Ledger
  -> Object Map + Learning Path
  -> Extract / Verify / Compile
  -> Field-Aware Skill Retrieval + Abstention
  -> Runtime Outcome / Correction Ledger
  -> Recurring Experience Candidate
  -> Frozen Eval + Human Keep/Revert
```

## 2. 官方 Skill 标准

### Agent Skills

- 规范：[agentskills.io/specification](https://agentskills.io/specification)
- Anthropic 说明：[Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- 官方仓库审计 Commit：`anthropics/skills@b29e7cf65e5cb78a5ac33d582270551bc74a14eb`

可采纳：

- `name`、`description` 是必需字段；
- `license`、`compatibility`、`metadata`、`allowed-tools` 是合法可选字段；
- `name` 必须与父目录一致；
- metadata → SKILL.md → references/scripts/assets 三级渐进披露；
- 主 SKILL.md 建议不超过 500 行；
- 从真实任务评测开始，再增量构建 Skill；
- Skill 安装前必须审查脚本、依赖、资源和网络行为。

本轮落地：

- validator 不再错误拒绝官方可选 frontmatter；
- 支持 `description: |` / `>` 多行值；
- 校验目录名与 `name` 一致；
- 毛泽东实例采用 145 行入口 + 按需 references，不再生成超长单文件人格提示。

## 3. GitHub 与 Hugging Face 架构

| 项目 | 关键设计 | one-skills 决策 |
|---|---|---|
| [Corpus2Skill](https://github.com/dukesun99/Corpus2Skill) `e1f0361` | 编译期嵌入+层级聚类；运行期由 Agent 导航 SKILL/INDEX，再按 ID 取全文 | 采纳层级导航、摘要卡、实体跳转和渐进披露思想；不删除现有全文/向量/图召回 |
| [AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs) `773a529` | `research-state.yaml`、findings、日志、文献与实验分离，跨会话保持约束 | 采纳“研究状态与结论分离”；Source Catalog 与 Evidence Ledger 承担稳定状态 |
| [SkillHone](https://github.com/Tencent/SkillHone) | 每次诊断、修改、证据、评测和决议进入持久决策历史；Skill 与 Eval 分仓 | 采纳 append-only Experience Ledger 和候选历史；完整 Git keep/revert 棘轮列为 P1 |
| [MemSkill](https://github.com/ViktorAxelsen/MemSkill) `9907c35` | Controller 选择可学习 memory skills，Designer 根据 hard cases 演进，奖励稳定后回滚 | 采纳 hard-case/复现/回滚原则；不引入 PPO 依赖 |
| [AutoSkill](https://github.com/ECNU-ICALK/AutoSkill) | 从交互轨迹抽取、合并、版本化并动态注入 Skill | 采纳 correction/outcome 经验入口；禁止单次失败直接改 Skill |
| [OpenSkill](https://github.com/OpenLAIR/OpenSkill) | 从开放网络同时获取知识与验证锚点；构建阶段与目标评测隔离 | 采纳 `verification_anchor` 与 `evaluation_only` 角色和泄漏屏障；其代码尚未发布，不复制宣传性实现 |
| [ReasoningBank](https://arxiv.org/abs/2509.25140) | 从成功和失败轨迹提炼通用推理记忆，再召回到新任务 | 采纳成功/失败均可记录；候选需多次独立证据 |
| [MUSE-Autoskill](https://arxiv.org/html/2605.27366v1) | Skill 生命周期、长期记忆、Skill 级经验和运行反馈统一 | 与 Knowledge/Skill/Recipe 三环一致；补足 Skill 级经验账本 |

## 4. neo-skills / cangjie-skill / nuwa-skill 复审

### neo-skills v0.2.8

审计范围：`104f966`（v0.2.2）到 `d88f6db`（v0.2.8），新增约 5,330 行。

新增设计：

- 可解释、可拒答 Object Router；
- Guided 事件撤回、无正文 tombstone；
- Guided → Pack 版本同步和隐私清除；
- 统一 `status/gate/allowed_actions` 控制面；
- 跨 Runtime JSON Harness Adapter；
- Skill Hash 绑定测试结果；
- 用户确认的 Git Evolution Ratchet。

本轮采纳：

- 实现可拒答 `one route`；
- Pack 来源更新会归档旧提取产物、清除旧 quote，并把非活动版本 Claim 标为 superseded；
- 明确输出变更候选而不自动进化。

尚待吸收：

- `status/gate/allowed_actions` 统一机器控制面；
- Guided → Pack 的预览令牌、事件撤回与 privacy purge；
- 当前 Skill Hash 绑定 Answer Agent 结果；
- Git candidate commit + 用户 token keep/revert + 中断恢复。

不照搬：

- neo-skills 为单 Pack 文件协议，明确不使用数据库/API/队列；one-skills 已有跨 Pack 知识库、ACL、API 和 Worker，不能倒退。

### cangjie-skill

- 审计 Commit：`55e4b7059c423534f94cfbdeb0a4ee34f3ba6182`
- 关键贡献仍是 Adler 全局地图、五视角提取、三重验证、RIA++、Zettelkasten、兄弟诱饵测试和 Digest。

本轮新增认识：

- “推荐学习顺序”不能只留在 INDEX 文本，应变成 `LEARNING_PATH.json`；
- V1 的“不同语境复现”与“独立来源佐证”是两件事，系统必须分别记录；
- 25 个相似原子 Skill 在大型库中会增加 shadowing，原子化要与入口路由和字段召回一起设计。

### nuwa-skill

- 审计 Commit：`27642f5bfed2dc1bbf8ee59a2c1ee602a626bbd7`
- 关键贡献仍是六维人物调研、长文优先、反复出现、他者批评、决策行为、时间变化、表达 DNA、内在张力和诚实边界。

本轮新增认识：

- 人物质量不能通过“出现了局限/来源等关键词”证明；
- URL 个数不等于独立来源数，同一材料跨维度重复也不能增加权威；
- 人物公开文本、编辑整理稿、异方记录、二手研究和模型推断必须有不同直接性；
- 对历史人物，严重失败不是“负面评价附录”，而是方法适用边界的一部分。

## 5. 检索与知识库论文

### Skill Retrieval Augmentation

- [Skill Retrieval Augmentation for Agentic AI](https://arxiv.org/html/2604.24594v3)
- SRA-Bench 把失败拆成 retrieval、incorporation、application；26,262 个 Skills 的实验表明，召回正确 Skill 仍不代表 Agent 知道何时加载。

架构含义：

- `one skill-search` 只证明候选召回，不证明运行效果；
- 必须输出 score、margin 和 abstain/confirm；
- 后续评测分别记录 Recall/NDCG、加载率、最终任务成功率。

### Field-Aware Retrieval

- [Field Aware Agent Skill Retrieval](https://arxiv.org/html/2608.02880v1)
- 将 name、description、body 等字段分开做 sparse/dense 相似，再学习组合，优于直接拼接；库越大优势越明显。

本轮落地：

- 单独索引 `name/description/triggers/anti_triggers/procedure/body`；
- 每字段输出 lexical/semantic/combined；
- top score 和 top-two margin 均有门；
- 显式 Skill 名称调用有确定性优先级。

### Generic Background Bias

- [SkillSight](https://arxiv.org/html/2607.18785v2)
- 大量 Skill 共享“输入、步骤、使用”等背景文本，会淹没真正区分能力的词。

本轮落地：

- 词项分使用 IDF 校准通用背景；
- 反触发只用明确 lexical overlap 降权，避免“边界写得越完整，召回越差”；
- 子标题继承父字段，避免工作流被三级标题切断。

### RAG / Memory

- [HippoRAG 2](https://arxiv.org/html/2502.14802v1)：dense-sparse + passage graph + PPR 同时覆盖事实、关联和 sense-making。
- [When to use Graphs in RAG](https://arxiv.org/html/2506.05690v3)：GraphRAG 的优势依赖任务复杂度，简单事实查找不应承担高图构建成本。
- [T2RAG](https://arxiv.org/html/2508.02435v1)：用原子三元组和迭代槽位解析降低完整知识图构建成本。

决策：

- 保留 FTS + dense + lineage RRF；
- 不把所有来源强制 LLM 建图；
- Claim-Key 为高质量、人工可审计的关系入口；
- P1 再对 multi-hop benchmark 比较 PPR/三元组检索，未测前不引入图数据库。

## 6. 来源发现与引用可靠性

### 研究证据

- [Cited but Not Verified](https://arxiv.org/html/2605.06635v1)：链接可访问、内容相关和事实支持是三个不同维度；检索更多不保证引用更准。
- [Training Documents Reranker with Search Rubrics](https://arxiv.org/html/2608.03527v1)：深度研究需要的是权威、覆盖、多样、简洁的文档集合，不是单篇 relevance Top-K。
- [STAMP](https://arxiv.org/html/2607.11172v1)：证据到文档再到搜索步骤的 provenance 可用于信用分配。
- [OpenSkill](https://arxiv.org/html/2606.06741v1)：知识源和验证锚点分离，目标评测在构建期间不可见。

### Source Catalog 1.0

每个候选来源必须声明：

- `ingest`：实际进入系统的捕获文件或 URL；
- `uri/locator/creator`：可回查身份；
- `authority`：primary / official / scholarly / reputable-secondary / community / unknown；
- `directness`：direct / derived / tertiary / unknown；
- `independence_group`：不能用 URL 数冒充独立来源数；
- `role`：evidence / context / counterevidence / verification_anchor / evaluation_only；
- `coverage`：覆盖哪个研究问题；
- `temporal_scope/published_at`：时效要求；
- `license/usage_rights/access`：权限边界。

集合门检查独立组、一手来源、角色覆盖、研究问题覆盖、质量均值和 holdout。`SOURCE_QUALITY.json` 哈希进入 `PROTECTED_CONSTRAINTS.json`。

### 网络采集流程

```text
研究问题
  -> 查询矩阵（主题 × 来源角色 × 时间）
  -> 候选目录，不直接进 Pack
  -> 去重与 independence_group
  -> 可访问、权威、直接性、时效、许可评分
  -> 文档集合覆盖检查
  -> 捕获正文/短引并冻结 Hash
  -> evaluation_only 隔离
  -> Pack Ingest
```

搜索摘要只能用于发现，不能作为最终证据。网页抓取失败时不得假装已读。

## 7. 学习结构

### 研究证据

- [Hey Chat, Can You Teach Me?](https://arxiv.org/html/2606.11744v1)：把先修知识建成图，将“教什么”和“怎样苏格拉底式对话”分离，显式课程结构优于只扩大底模。
- [IntelliCode](https://arxiv.org/html/2512.18669v1/)：版本化 learner state、single-writer、掌握度、误解、提示和间隔复习。
- [EduClaw-Bench](https://arxiv.org/html/2608.03206v1)：教学质量应按长周期学习增益评估，不是单轮回答流畅度。

本轮落地：

- 每个 Pack 生成 `LEARNING_PATH.json`；
- 编译前按源结构顺序，编译后按 capability prerequisite；
- 节点包含 objectives、mastery_checks、source_locators；
- `one learn init/record/next/status` 保存独立 learner state；
- 正确尝试进入 1/3/7/14/30 天复习间隔；
- 学习证据不修改知识源和 Skill。

尚未实现：

- 对误解类型的模型化；
- 基于真实学习增益训练课程策略；
- 多学习者隐私和服务端并发控制。

## 8. 经验与进化

### 研究证据

- [Learning on the Job](https://arxiv.org/html/2607.22157v1)：部署结果和纠正可蒸馏成外部自然语言规则，冻结模型也能持续学习。
- [ReasoningBank](https://arxiv.org/abs/2509.25140)：成功与失败都能形成通用推理记忆。
- [MemSkill](https://arxiv.org/html/2602.02474)：hard-case buffer、代表案例挖掘、探索新技能、稳定奖励后早停/回滚。
- [SkillHone](https://arxiv.org/html/2606.08671v2)：保留诊断、修订、证据、结果和被拒方案，而非只保留最终文件。

本轮落地：

- `EXPERIENCE_EVENTS.jsonl` append-only；
- outcome 为 success/failure/corrected；
- training 与 evaluation 物理分组；
- 至少两次、两个 evidence locator 的复现才形成候选；
- 候选只写 `EXPERIENCE_CANDIDATES.json`，不会自动修改 Skill；
- 晋升说明强制冻结测试、before/after 和人工 keep/revert。

## 9. 毛泽东实例反推的代码缺陷

| 缺陷 | 证据 | 修复 |
|---|---|---|
| 中文独特性永远偏低 | `summary.split()` 对无空格中文常只有1项 | 改用中英文 tokenizer，并加回归测试 |
| 同一文档不同章节与独立来源混淆 | V1 只存 section_path | 分开 `source_contexts/source_ids/independence_groups/source_independent` |
| 语义自动合并会误并边界概念 | 高相似候选实际属于版本、权利、信息失灵等不同概念 | 不降低阈值；新增显式 Claim-Key |
| 更新后旧 quote 留在账本 | `extract_pack()` 直接 append | 更新前归档；保留非 quote 人工证据；重建 quote |
| DB Claim 不随 Source Version 失效 | active Claim 仍连到旧 Chunk | 只由非活动版本支持的 Claim 标 `superseded` |
| Skill 边界写得越多召回越差 | anti-trigger semantic 与正向领域天然相似 | 反触发仅按明确 lexical overlap 惩罚 |
| 子标题切断字段 | `###` 被当成新 body | 子标题继承父字段 |

## 10. 未采纳或暂缓

- **完全用层级导航替代检索**：Corpus2Skill 是早期实现；one-skills 需要同时支持简单事实、跨 Pack、ACL 和图关系，保留混合路线。
- **所有文档自动建知识图**：成本和错误传播尚无稳定收益；先用显式 Claim、Lineage 和任务路由。
- **单次反馈自动改 Skill**：容易把偶然错误、恶意反馈或 holdout 泄漏写成规则。
- **纯 LLM 自评**：Skill 生态研究和 nuwa 自身引用均提示自评不可靠；必须保留独立结果和人工门。
- **用 Star 作为质量分**：Star 只能说明传播，不证明事实、路由、任务效果或安全。
- **为“蒸馏万物”统一一个最终模板**：继续坚持统一 IR + 类型化 Profile，不牺牲对象真实性标准。

## 11. 后续优先级

### P0，本轮完成

- Source Catalog / Source Quality Gate / holdout；
- Claim-Key；
- 官方 Agent Skills frontmatter；
- Field-aware skill retrieval；
- Learning Path / Learner State；
- Experience Ledger；
- 中文门与增量失效修复；
- 毛泽东候选 Skill 与社区对比。

### P1

- 统一 `one status/gate/allowed_actions`；
- Guided → Pack 同步预览和 privacy purge；
- Skill Hash 绑定 Answer Agent 结果；
- 用户确认的 Git Evolution Ratchet；
- SkillRet/SRA-Bench 子集和 incorporation 指标。

### P2

- multi-hop 检索基准后再决定 PPR/HippoRAG2；
- 来源发现 Provider 插件和 citation AST；
- learner misconception 与长期学习增益 benchmark；
- 经验候选的语义聚类、冲突合并和跨模型迁移。

## 12. v0.3 重新审计：基础设施不等于蒸馏质量

审计基线：

- one-skills：`bd8cb39559c2d6a963ef19d99a7cbb962ebb41ca`
- Cangjie 方法论：`kangarooking/cangjie-skill@149cb39f559cafcb82910f8662b3f4e3b9ee5574`
- Cangjie 毛泽东产物：`chinapathbreaker/mao-skill@0c127bd235018e1e8b243dd0a72c6f288a560e2e`

v0.2 已证明来源、版本、权限和发布门可以工程化，但毛泽东案例证明
“门禁完整”不能替代“能力理解和编译完整”。以下缺口均可从冻结产物复现：

1. `OBJECT_MAP.md` 的地图维度仍全部是“待提取”，没有 Object Overview；
2. `atomic-network` 只是 Profile 元数据，实际编译器仍为每个候选套同一模板；
3. `INDEX.md` 必须人工补写，流水线自身不能生成候选知识图、原子关系和学习路线；
4. 默认测试是通用占位句，无法证明真实触发、模块区分或任务增益。

因此 v0.3 的主问题从“是否有知识库”改为：

> 系统能否从完整对象中形成有证据的整体理解，把案例、反例、术语和方法合并为
> 不碎片化的能力网络，并通过 no-skill 与开源基线的真实任务对照证明增益？

### 12.1 新研究结论

- [SkillLens](https://arxiv.org/abs/2605.23899) 把 Skill 生命周期拆为
  experience generation、skill extraction 和 skill consumption，并用
  `with-skill - baseline` 衡量真实增益。v0.3 不再用静态结构分冒充效果。
- [Trace2Skill](https://arxiv.org/abs/2603.25158) 对一批成功/失败轨迹并行分析，
  再层级合并为无冲突 Skill。v0.3 将相同思想用于多来源候选整合。
- [SKILL-KD](https://arxiv.org/abs/2607.28048) 从 student failure 与 teacher
  trajectory 的差异生成 trace-linked patch，并用 drift-aware consolidation
  防止局部修补造成膨胀和破坏性更新。
- [Skill-Alpha](https://arxiv.org/abs/2608.01678) 使用
  `CREATE/UPDATE/MERGE/PRUNE/NOOP` 和 downstream rollback reward。
  v0.3 采用编辑协议和 before/after 门，不在本项目训练 GRPO。
- [ContinualSkillBench](https://arxiv.org/abs/2608.03874) 显示长期积累中的
  Skill 碎片化会损害弱模型。v0.3 使用顶层入口加内部模块，不把全部原子模块
  暴露到全局 Skill 库。
- [Field Aware Agent Skill Retrieval](https://arxiv.org/abs/2608.02880) 和
  [More Skills, Worse Agents?](https://arxiv.org/abs/2605.24050) 共同支持：
  大型 Skill 库的主要风险是选择错误而非单纯上下文长度。

### 12.2 v0.3 决策

```text
Source candidates
  -> source-set gate
  -> evidence-linked Object Overview
  -> Profile-specific multi-view extraction
  -> hierarchical candidate consolidation
  -> V1/V2/V3 + human portfolio confirmation
  -> one public router + internal atomic modules
  -> capability graph / glossary / digest / learning path
  -> no-skill / Cangjie / one-skills blind comparison
  -> structured patch + rollback + user keep/revert
```

七类 Profile 必须有不同的 extractor、compiler 和 evaluation contract；
“统一 IR”只统一证据和生命周期，不再统一最终内容模板。
