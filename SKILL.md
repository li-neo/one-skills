---
name: "one-skills"
description: "Distills people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills. Invoke when users ask to distill, create, repair, validate, or evolve a skill."
---

# one-skills

将人、内容、方法、流程或既有 Skill 转换为可运行、可验证、可追溯的 Agent Skills。

## 核心规则

1. 不把摘要当作 Skill。
2. 不在缺少材料时凭模型记忆完成蒸馏。
3. 证据、推导和假设必须分开标记。
4. 每个能力必须包含触发、执行、完成标准和边界。
5. 必须测试正例、反例、边界例和相邻 Skill 冲突。
6. 生成者不能独自完成最终评分。
7. 私人个体必须先确认授权和使用范围。
8. 进化优先直接调用 Darwin，不重复实现优化器。
9. 深度蒸馏先建立 Source Catalog；搜索摘要只能发现来源，不能充当证据。
10. 不把同一来源的多个章节、镜像或转述计为独立来源。
11. 构建材料与 `evaluation_only` holdout 必须隔离。
12. 内容/方法论默认使用一个公开入口加内部原子模块，不把相近模块全部暴露到全局召回。
13. 静态结构分不能证明效果；发布必须比较 no-skill、冻结 baseline 和 candidate。

## 入口路由

先根据用户目标选择 Profile：

| 用户目标 | Profile |
|---|---|
| 蒸馏自己、家人、同事、老板、名人或历史人物 | `person` |
| 蒸馏书籍、课程、播客、访谈、长文或字幕 | `content` |
| 蒸馏理论、框架、原则或完整方法论 | `methodology` |
| 整理操作手册、录屏、工单或隐性流程 | `sop` |
| 从需求文档创建 Skill，或修复现有 Skill | `skill` |
| 人物、资料、案例、工具和流程混合 | `hybrid` |
| 输入暂时无法分类 | `auto` |

无法唯一判断时，先运行 `one route --intent <minimal-intent>`。返回
`needs_confirmation=true` 时，只展示最多三个候选和最多两个确认问题，不创建
Workspace。

## Phase 0：建立蒸馏契约

确认或合理默认以下字段：

- 蒸馏对象
- 目标用途
- 受众
- 聚焦范围
- 可用材料
- 是否允许联网补充
- 授权和隐私范围
- 交付形式
- 成功标准
- 快速、标准或深度档位

以下情况必须暂停并询问：

- 用户未提供材料，且要求蒸馏非公开对象
- 涉及未授权私聊、秘密录音或敏感个人信息
- 无法判断用户要摘要、方法论还是可运行 Skill
- 成功标准会显著改变产物结构

如果目标明确但材料不足，不要一次抛出长表单。使用 `one guide init` 启动可恢复会话，每轮最多询问三个问题；将自述、情景回答、观察行为、文档结果和模型推断分级记录。至少确认 `scope` 与 `evidence_inventory` 后，才使用 `one guide create-pack` 进入正式十阶段 Pipeline。完整协议见 [Guided Distillation](docs/GUIDED_DISTILLATION.md)。

输出 `DISTILLATION_CONTRACT.md`。如果当前任务只要求设计方案，不创建虚假的输入和测试结果。

## Phase 1：建立来源账本

标准/深度任务先按 [来源质量协议](docs/SOURCE_QUALITY.md) 建立
`SOURCE_CATALOG.json`，再运行 `one source audit`。对每个来源记录：

- 来源 ID
- 文件、URL 或内容定位
- 作者和时间
- `authority` 与 `directness`
- 独立来源组，不按 URL 个数计数
- evidence、context、counterevidence、verification anchor 或 evaluation only 角色
- 对研究问题的覆盖
- 许可证和发布范围
- 隐私等级
- 哈希或版本

重要结论必须能回指来源位置。`evaluation_only` 不进入构建语料。高质量人工捕获
可以用 `Claim-Key` 显式声明跨来源同一主张；系统必须验证声明一致和独立来源组，
不得靠降低语义阈值强行合并。

本地、GitHub、Hugging Face 或外部搜索结果先通过 `one source discover` 进入
`SOURCE_CANDIDATES.json`。发现结果不能自动摄取，必须 shortlist 后再进入 Catalog。

## Phase 2：建立对象地图

先整体理解，再提取局部能力。

| Profile | 对象地图 |
|---|---|
| `person` | 时间线、领域、关键决策、观点演化、表达场景、矛盾 |
| `content` | 主旨、结构、概念、论证、案例、反例 |
| `methodology` | 目标、假设、机制、步骤、边界 |
| `sop` | 角色、前置条件、系统、状态、异常、交接 |
| `skill` | 承诺能力、触发、工作流、资源、测试、问题 |

输出 `OBJECT_OVERVIEW.json/md`，包含对象主旨、骨架、术语、
机制链、张力、局限、来源覆盖和研究缺口。确认 Overview Hash 后再进入语义验证。

## Phase 3：提取候选能力

从材料中提取：

- 能力与问题解决模式
- 框架、模型和原则
- 操作步骤和决策分支
- 触发与反触发条件
- 案例、反例和失败模式
- 边界、风险和降级路径
- 术语和概念关系
- 可定位证据

按 ProfileSpec 的互不重叠视角并行提取；不支持并行时串行执行，并保持相同产物结构。
长语料按自然章节 map，每块都携带 Object Overview，再层级 reduce。输出
`CANDIDATE_PORTFOLIO.json/md`，同义候选合并，冲突候选并列，案例/反例/术语降级为支持节点。

## Phase 4：验证候选

每个候选依次检查 V1/V2/V3：

1. **证据**：有可定位来源吗？
2. **语境复现**：是否跨场景或时间重复出现？
3. **来源独立**：人物或混合对象是否有两个独立 provenance group？
4. **生成力**：能处理材料未直接回答的新问题吗？
5. **独特性**：是否超越通用常识？
6. **可执行性**：能转成 Agent 步骤吗？
7. **边界**：知道何时失效吗？

结果只能是：

- `accepted`
- `downgraded`
- `rejected`
- `needs_evidence`

保留淘汰原因，不静默删除。

Builder、Answer Agent、Judge 使用隔离角色。只有一个模型时也必须分开会话和上下文，
并标记 `model-shared/session-separated`。验证结果写入
`VERIFIED_PORTFOLIO.json/md`；确认 Portfolio Hash 后才能编译。

## Phase 5：构建能力单元

每个接受的能力必须包含：

```text
Problem → Trigger → Input → Procedure → Output → Done
                       ↓
               Boundary / Failure / Fallback
                       ↓
                  Evidence / Confidence
```

能力之间标记：

- `depends_on`
- `contrasts_with`
- `composes_with`
- `conflicts_with`
- `routes_to`

## Phase 6：生成 Skill Pack

按 ProfileSpec 编译。内容和方法论默认生成双层网络：

```text
one public SKILL.md
  -> capabilities/*.json
  -> references/modules/*.md
  -> evals/modules/*.json
```

只有总入口参与全局 Skill Retrieval；内部模块在 Skill 已加载后进行二阶段路由。

文件分工：

- `SKILL.md`：高频执行规则、触发、步骤、边界
- `references/`：证据、背景、详细方法
- `scripts/`：可重复工具
- `evals/`：测试集
- `manifest.yaml`：来源、版本、授权和兼容信息

不要把全部研究材料塞入 `SKILL.md`。

## Profile 专项要求

### person

提取心智模型、决策启发式、表达 DNA、价值观、反模式、内在张力和诚实边界。

默认输出 `advisor` 模式。只有用户明确需要且授权允许时，才启用 `voice` 模式。

对自己、家人、同事或老板：

- 优先蒸馏工作能力和决策方法
- 不推断敏感人格、健康或私人关系
- 不允许 Skill 冒充本人授权或承诺
- 标记 `self`、`consented`、`work-authorized`、`public-only` 或 `prohibited`

### content

摘要只是副产物。核心产物是原子方法论 Skills、术语表、关系图、测试和
`LEARNING_PATH.json`。原课程或原书有明确递进时，先保留源顺序；Skill 编译后再
用 `depends_on` 补先修关系。

### methodology

必须明确目标问题、成立假设、诊断、执行、分支、完成标准、失效条件和误用案例。

### sop

每一步必须有执行主体、输入、输出和完成标准。删除、迁移、发布等跨系统动作必须形成完整闭环。

### skill

支持 `create`、`extract`、`repair`、`refactor` 和 `evaluate`。重构时不得静默改变核心用途。

## Phase 7：验证

至少执行：

1. Frontmatter 和文件结构检查
2. `should_trigger`
3. `should_not_trigger`
4. `edge_case`
5. `sibling_conflict`
6. 核心任务行为测试
7. 失败恢复测试
8. 安全、隐私和来源检查

安全、授权、反触发和相邻 Skill 冲突默认要求 100% 通过。

优先使用独立答题 Agent 和独立评分 Agent。至少同题比较 `no-skill / frozen baseline /
candidate`，保存完整回答、Judge 理由、模型角色、Suite/Source/Skill/Answer Hash、
token 和延迟。独立 Provider 不可用时允许同模型隔离会话，但必须降低验证等级。

## Phase 8：交付

交付前确认：

- Skill 已通过门禁
- 来源和截止时间清晰
- 已知限制已记录
- 测试可以复跑
- 目标 Runtime 能发现并触发 Skill
- 未把内部或敏感来源发布到公开产物

## Phase 9：进化

如果用户要求优化或持续进化：

1. 保留 one-skills 的规范化测试集。
2. 生成当前 Darwin 版本兼容的 `test-prompts.json`。
3. 将授权、安全、来源和反触发条件设为受保护约束。
4. 直接调用 Darwin 执行基线、实验、paired 评审和 keep/revert。
5. 重复失败才生成 `CREATE/UPDATE/MERGE/PRUNE/NOOP` whole-folder patch。
6. 每个 patch 必须绑定训练轨迹、before/after Hash、protected gates、快照和用户 keep/revert。
5. Darwin 完成后重新运行 one-skills 回归门禁。

不得为了通过测试而降低测试难度或删除失败案例。

运行反馈先用 `one experience record` 写入 append-only 账本。单次失败不能改
Skill；至少两次独立 evidence locator 复现后，才用 `one experience mine`
形成候选。`evaluation` 事件不参与候选挖掘。完整协议见
[学习路径与经验进化](docs/LEARNING_AND_EXPERIENCE.md)。

## 失败与降级

| 触发条件 | 一线处理 | 仍失败时 |
|---|---|---|
| 来源不足 | 缩小范围并降低置信度 | 只交付研究缺口 |
| 来源冲突 | 按时间和场景拆分 | 人工裁决 |
| 无 sub-agent | 串行提取和测试 | 标记独立性降低 |
| 上下文不足 | 分 Phase 落盘续跑 | 从状态文件恢复 |
| 无法自动测试 | 静态检查和人工测试 | 标记未通过自动验证 |
| Skill 抢触发 | 增加冲突测试 | 拆分、合并或加入路由器 |

## 反模式

- 凭记忆蒸馏
- 把摘要包装成 Skill
- 把通用常识包装成独特能力
- 只测正例
- 同一 Agent 自改自评
- 模仿表达却没有复制判断方法
- 消除真实矛盾
- 未授权蒸馏私人个体
- 把规划接口写成已实现能力
- 为了通用性制造巨型 Skill

## 进度与恢复

长任务每完成一个 Phase，更新 `pack.json.lifecycle`：

- 当前 Phase
- 已完成产物
- 待处理问题
- 被阻塞项
- 下一步
- 最后更新时间

恢复时先读取状态和已有产物，不重复已完成工作。

## 最小执行契约

以下硬约束吸收自姊妹项目与 2026 年检索、来源和学习研究，任何 Skill 交付都必须满足。完整规范见 `docs/ARCHITECTURE.md` 第 19、20 章。

1. **Frontmatter**：必需 `name` 与 `description`；允许官方规范的 `license / compatibility / metadata / allowed-tools`；name 与父目录一致。
2. **Pipeline 状态机**：十阶段 `contract→ingest→map→extract→verify→compile→link→test→ship→evolve` 由 `pack.json.lifecycle` 持久化，不能跳阶。
3. **证据 Schema**：`EVIDENCE_LEDGER.jsonl` 每条必须含 `id / claim / evidence_type / source / locator / confidence[0,1] / inference_level / permission`；`evidence_type` 使用 `schemas/evidence.schema.json` 的封闭枚举，自述和情景回答不得冒充观察行为或已记录结果。
4. **测试覆盖**：`test-prompts.json` 必须至少含 `should_trigger / should_not_trigger / edge_case`；静态检查永远不填 `actual_effect` 分，只有独立 Agent 结果才折算。
5. **交付读回**：安装、导出、切换 `active_version` 后必须读回校验；覆盖已存在目标须先 `.backup-<timestamp>`。
6. **URL 安全**：默认拒绝私有/环回/链路本地 IP，重定向后再校验；URL ≤20 MiB，本地文件 ≤100 MiB。
7. **Darwin 降级**：无 Darwin 时只写 `DARWIN_REQUEST.md` 并保持 `status: prepared`，不得声称"已进化"。
8. **来源质量**：Catalog-backed Pack 必须通过来源集合门，质量报告写入 `SOURCE_MANIFEST.json.quality`，哈希冻结在 `pack.json.reproducibility`。
9. **学习结构**：Pack 必须包含无环 `LEARNING_PATH.json`。
10. **Skill 召回**：大型 Skill Bank 使用字段感知召回；低分或低 margin 必须确认或拒答。
11. **经验进化**：部署反馈只生成候选；holdout 不参与挖掘，用户确认前不修改 Skill。
12. **核心质量**：v0.4 双层网络发布前，可靠性、完整性和准确率硬门必须分别通过，不允许总分补偿失败维度。
