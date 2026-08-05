---
name: "neo-skills"
description: "Distills people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills. Invoke when users ask to distill, create, repair, validate, or evolve a skill."
---

# neo-skills

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

无法唯一判断时，展示最多三个候选 Profile、判断依据和产物差异，再让用户选择。

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

输出 `DISTILLATION_CONTRACT.md`。如果当前任务只要求设计方案，不创建虚假的输入和测试结果。

## Phase 1：建立来源账本

对每个来源记录：

- 来源 ID
- 文件、URL 或内容定位
- 作者和时间
- 一手、二手或用户陈述
- 许可证和发布范围
- 隐私等级
- 哈希或版本

重要结论必须能回指来源位置。

## Phase 2：建立对象地图

先整体理解，再提取局部能力。

| Profile | 对象地图 |
|---|---|
| `person` | 时间线、领域、关键决策、观点演化、表达场景、矛盾 |
| `content` | 主旨、结构、概念、论证、案例、反例 |
| `methodology` | 目标、假设、机制、步骤、边界 |
| `sop` | 角色、前置条件、系统、状态、异常、交接 |
| `skill` | 承诺能力、触发、工作流、资源、测试、问题 |

输出 `OBJECT_MAP.md`，并列出信息缺口。

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

支持 sub-agent 时按互不重叠的视角并行提取；不支持时串行执行，并保持相同产物结构。

## Phase 4：验证候选

每个候选依次检查：

1. **证据**：有可定位来源吗？
2. **复现**：是否跨来源、场景或时间重复出现？
3. **生成力**：能处理材料未直接回答的新问题吗？
4. **独特性**：是否超越通用常识？
5. **可执行性**：能转成 Agent 步骤吗？
6. **边界**：知道何时失效吗？

结果只能是：

- `accepted`
- `downgraded`
- `rejected`
- `needs_evidence`

保留淘汰原因，不静默删除。

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

按职责决定生成单 Skill 或 Skill Pack。

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

摘要只是副产物。核心产物是原子方法论 Skills、术语表、关系图和测试。

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

优先使用独立答题 Agent 和独立评分 Agent。独立 Agent 不可用时，明确标记验证等级降低，不声称完成双盲验证。

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

1. 保留 neo-skills 的规范化测试集。
2. 生成当前 Darwin 版本兼容的 `test-prompts.json`。
3. 将授权、安全、来源和反触发条件设为受保护约束。
4. 直接调用 Darwin 执行基线、实验、paired 评审和 keep/revert。
5. Darwin 完成后重新运行 neo-skills 回归门禁。

不得为了通过测试而降低测试难度或删除失败案例。

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

长任务每完成一个 Phase，更新 `PIPELINE_STATE.md`：

- 当前 Phase
- 已完成产物
- 待处理问题
- 被阻塞项
- 下一步
- 最后更新时间

恢复时先读取状态和已有产物，不重复已完成工作。
