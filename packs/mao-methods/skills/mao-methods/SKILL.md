---
name: mao-methods
description: Routes an explicitly requested methodology to evidence-linked internal modules. Use when the user wants to diagnose and act with that method; stop when assumptions, evidence, law, or safety gates fail.
compatibility: Requires file reading; current-fact tasks also require web or data access.
metadata:
  one-skills.activation: explicit
  one-skills.aliases: mao-methods,毛泽东方法,毛选方法,用毛选,毛泽东著作方法
allowed-tools: Read
---

# 证据化方法工具

运行方法结构，不模拟作者身份，不把历史或理论断言冒充现实效果。

## 激活门

首次加载只在用户明确点名 `mao-methods`、其 alias 或明确要求该对象的方法时发生。
Runtime 已加载本 Skill 后，后续消息不需要重复点名，应直接按模块路由。
普通事实、日常选择、翻译或创作请求应退出本 Skill，但退出不等于拒答：将
`would_trigger` 设为 false、模块声明置空，再用 Runtime 的正常能力继续完成原请求；
信息不足时提出一个最小澄清问题。

## 模块路由

先检查成立假设，再按问题类型选择一个主模块和最多一个辅助模块。

| 当前问题 | 模块 | 读取 |
|---|---|---|
| 理论、上级转述或既有文本与可核验事实冲突 | `anti-dogmatism-correction` | [读取模块](references/modules/anti-dogmatism-correction.md) |
| 组织需要聚焦，但多个底线和必要协同不能停止 | `center-work-coordination` | [读取模块](references/modules/center-work-coordination.md) |
| 多个问题争夺注意力，当前优先项不清楚 | `contradiction-reclassification` | [读取模块](references/modules/contradiction-reclassification.md) |
| 总体数据、高频声音或资源聚焦掩盖无发言权群体承担的局部损害 | `distribution-before-aggregate` | [读取模块](references/modules/distribution-before-aggregate.md) |
| 组织收集了意见，但没有形成可修正的方案与结果返回 | `feedback-integrity` | [读取模块](references/modules/feedback-integrity.md) |
| 重要结论主要来自转述、单一样本或管理层想象 | `investigation-before-judgment` | [读取模块](references/modules/investigation-before-judgment.md) |
| 方法结论停留在解释层，无法被现实结果推翻 | `practice-test-loop` | [读取模块](references/modules/practice-test-loop.md) |
| 坏消息会使报告者受罚，决策系统只能收到支持性信息 | `protected-dissent-channel` | [读取模块](references/modules/protected-dissent-channel.md) |
| 复杂问题被简化为某个人或群体有问题 | `relational-problem-map` | [读取模块](references/modules/relational-problem-map.md) |
| 历史战争、政治和运动语言被直接套到现代组织与个人 | `rights-bound-transfer` | [读取模块](references/modules/rights-bound-transfer.md) |
| 资源弱或不确定性高，却试图一次全面推进 | `stage-experimentation` | [读取模块](references/modules/stage-experimentation.md) |
| 公开定稿、现场记录、编辑文本和现代推断被混成作者原话 | `version-attribution` | [读取模块](references/modules/version-attribution.md) |

一次选择一个主模块，必要时最多组合一个辅助模块。内部模块不参与全局自动召回。

## 组合与依赖

| 主模块 | 关系 | 关联模块 |
|---|---|---|
| `anti-dogmatism-correction` | `depends_on` | `version-attribution` |
| `anti-dogmatism-correction` | `composes_with` | `practice-test-loop` |
| `center-work-coordination` | `depends_on` | `contradiction-reclassification` |
| `center-work-coordination` | `composes_with` | `stage-experimentation` |
| `contradiction-reclassification` | `depends_on` | `relational-problem-map` |
| `contradiction-reclassification` | `composes_with` | `practice-test-loop` |
| `distribution-before-aggregate` | `depends_on` | `investigation-before-judgment` |
| `distribution-before-aggregate` | `composes_with` | `feedback-integrity` |
| `feedback-integrity` | `depends_on` | `protected-dissent-channel` |
| `feedback-integrity` | `composes_with` | `practice-test-loop` |
| `investigation-before-judgment` | `depends_on` | `rights-bound-transfer` |
| `investigation-before-judgment` | `composes_with` | `practice-test-loop` |
| `practice-test-loop` | `depends_on` | `investigation-before-judgment` |
| `practice-test-loop` | `composes_with` | `stage-experimentation` |
| `protected-dissent-channel` | `depends_on` | `rights-bound-transfer` |
| `protected-dissent-channel` | `composes_with` | `distribution-before-aggregate` |
| `relational-problem-map` | `depends_on` | `investigation-before-judgment` |
| `relational-problem-map` | `composes_with` | `contradiction-reclassification` |
| `rights-bound-transfer` | `composes_with` | `protected-dissent-channel` |
| `rights-bound-transfer` | `composes_with` | `version-attribution` |
| `stage-experimentation` | `depends_on` | `practice-test-loop` |
| `stage-experimentation` | `composes_with` | `center-work-coordination` |
| `version-attribution` | `composes_with` | `anti-dogmatism-correction` |
| `version-attribution` | `depends_on` | `rights-bound-transfer` |

- `depends_on` 是前置检查，不占辅助模块槽位。条件未满足时先运行关联模块；
  条件已满足时只记录检查结果，不把它误报为辅助模块。
- `composes_with` 不是装饰关系。执行或决策请求中，只要关联模块的成立假设满足，
  就选择最相关的一个读取并运行；主模块工作流点名的组合目标优先。只有说明不适用
  理由后才能省略。
- 治理模块：`rights-bound-transfer`, `version-attribution`。出现其触发条件时强制应用，不计入“一个辅助模块”上限。
- 不得静默组合。若 Runtime 输出包含 `selected_module` 或路由声明，必须按
  `前置模块 + 主模块 + 辅助模块 + 治理模块` 显式列出本次实际运行的模块。

## 总工作流

1. 建立事实契约，区分已知、争议、未知和不可逆风险。
2. 把用户明确要求的要素列成输出检查项，不得在概括时遗漏。
3. 根据上表选择主模块，解析其直接依赖和组合关系，并读取实际运行的全部模块。
4. 运行模块步骤，保留备选解释、反证、改判、停止和回滚条件。
5. 应用全局治理门，再逐项核对用户要求后输出结果。

## 边界与全局治理门

- 成立假设不满足时停止
- 保留反证和改判条件
- 行动必须守法、可逆并可复核

任一硬门失败时，不扩大行动，只输出补证、治理修复或专业升级路径。

## 输出契约

包含问题、假设、机制、步骤、分支、完成、停止和回滚的执行结果。

用户明确要求的样本、反证、试验、底线、角色、停止或回滚条件均是强制检查项；
不得用相近概念或引用说明替代方案正文中的执行要素。

## 检查点

- 已区分事实、解释和现代迁移；
- 已显式声明前置检查、一个主模块、必要的辅助模块和已触发的治理模块；
- 已逐项覆盖用户明确要求，没有把关键动作只写在引用或限制说明中；
- 已保留反证、改判、停止和复核条件；
- 任一安全、法律、权利或来源硬门失败时已停止扩大行动。

## 失败与降级

- 事实不足：只给调查问题和条件式判断。
- 来源冲突：并列呈现，不强行调和。
- 高风险不可逆任务：停止执行并升级给有权限的人。

## 证据

每个模块在其“证据”章节列出支撑句和原始定位；汇总见
[references/evidence.md](references/evidence.md)，来源方法、版本和外推限制见
`references/source-notes/`。
