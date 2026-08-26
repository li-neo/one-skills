---
name: one-skills
description: Distill people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills. Invoke when users ask to distill, create, repair, validate, or evolve a skill.
---

# one-skills

将人、内容、方法、流程或既有 Skill 转换为可运行、可验证、可追溯的 Agent Skills。

本文件是**路由索引**：先定位对象与阶段，再按需读取 `references/` 下的完整协议。
完整执行前置见 [运行前置与降级](references/runtime.md)。

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

先根据用户目标选择对象类型：

| 用户目标 | 对象类型 |
|---|---|
| 蒸馏自己、家人、同事、老板、名人或历史人物 | `person` |
| 蒸馏客户、客户群或关键账户 | `customer` |
| 蒸馏产品/技术/商业/项目方案 | `proposal` |
| 蒸馏书籍、课程、播客、访谈、长文或字幕 | `content` |
| 蒸馏理论、框架、原则或完整方法论 | `methodology` |
| 蒸馏思想、理论或价值体系 | `thought-system` |
| 整理操作手册、录屏、工单或隐性流程 | `sop` |
| 从需求文档创建 Skill，或修复现有 Skill | `skill` |
| 人物、资料、案例、工具和流程混合 | `hybrid` |
| 输入暂时无法分类 | `auto` |

无法唯一判断时，先运行 `one route --intent <minimal-intent>`。返回
`needs_confirmation=true` 时，只展示最多三个候选和最多两个确认问题，不创建
Workspace。各对象类型的专项要求见 [Profile 专项要求](references/profiles.md)。

## 工作流

十阶段 `contract→ingest→map→extract→verify→compile→link→test→ship→evolve` 由
`pack.json.lifecycle` 持久化，不能跳阶。

| 阶段 | 最小产物 | 门 |
|---|---|---|
| contract | `DISTILLATION_CONTRACT.md` | 无占位符 |
| ingest | `SOURCE_CATALOG.json` / `SOURCE_MANIFEST.json` | 来源存在且角色/独立组确认 |
| map | `OBJECT_OVERVIEW.json/md` | Overview 已显式确认 |
| extract | `CANDIDATE_PORTFOLIO.json` / `EVIDENCE_LEDGER.jsonl` | 至少一条 Claim |
| verify | `VERIFIED_PORTFOLIO.json` | 至少一个 accepted 候选 |
| compile | `skills/<name>/SKILL.md` | 结构校验无错误 |
| link | `LEARNING_PATH.json` | 无环 |
| test | `evaluations/comparison-report.json` | 三条件盲测 valid+passed（standard/deep） |
| ship | `MODEL_CARD.md` + `DIGEST.md` | 测试门仍通过 |
| evolve | `evolution/DARWIN_REQUEST.md` | 已生成交接请求 |

每个阶段的完整步骤、命令与验证细节见 [十阶段 Pipeline 详解](references/pipeline.md)。
阶段门与统一推进见 [统一控制面与 Pack 阶段门](references/control-plane.md)。

```bash
one distill --source <dir> --type auto --mode standard --workspace .
one status <pack> --json       # 统一控制面：gate / allowed_actions / recommended_action
```

## 产物分离

Pack 根（溯源产物）与 `skills/<name>/`（唯一可发布单元）必须分层；Skill 目录必须
自包含，禁止 `../` 跨目录引用。完整规则、安装/导出命令与对比门分层见
[产物分离与交付](references/artifacts.md)。

## 进度与恢复

每完成一个 Phase 更新 `pack.json.lifecycle`，记录当前阶段、已完成产物、待处理问题、
被阻塞项与下一步。恢复时先 `one status <path> --json` 读取统一契约（
`recommended_action` / `gate` / `allowed_actions`），只执行白名单内动作；遇到
`blocked` 阶段按 `recommended_action.command` 或 `instruction` 继续，不重复已完成工作。

## 停止条件

以下任一情况必须暂停并向用户说明：

- 私人材料没有合理授权；
- 关键来源不可读或证据不足以支持所声称能力；
- 蒸馏目标将用于未经人工复核的高影响决定；
- 测试执行者与唯一评审者无法隔离；
- 发布会违反来源许可、版权或删除请求；
- 安装、外部写入或破坏性操作超出用户授权。

## 完成定义

只有当 Pack 通过契约、对象地图、模型验证、编译、触发、任务效果、安全/运行时和进化
棘轮相应质量门，且具备来源、边界、测试、版本和回滚点时，才报告"蒸馏完成"。否则准确
报告为草稿、候选、待验证或被阻塞。

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

## 最小执行契约

以下硬约束吸收自姊妹项目与 2026 年检索、来源和学习研究，任何 Skill 交付都必须满足。
完整规范见 `docs/ARCHITECTURE.md` 第 19、20 章。

1. **Frontmatter**：必需 `name` 与 `description`；允许官方规范的 `license / compatibility / metadata / allowed-tools`；name 与父目录一致。
2. **Pipeline 状态机**：十阶段由 `pack.json.lifecycle` 持久化，不能跳阶。
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
