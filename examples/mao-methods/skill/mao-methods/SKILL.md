---
name: mao-methods
description: Applies evidence-grounded methods distilled from Mao Zedong's public writings: investigation before judgment, contradiction mapping, frontline feedback loops, and staged focus. Use only when the user explicitly asks for 毛泽东/毛选方法, 调查研究, 主要矛盾, 从群众中来再验证, or a historically bounded comparison. Not for impersonation, political persuasion, enemy labeling, violence, personnel punishment, or ordinary history lookup.
license: Repository license not yet selected; source texts retain their original rights.
compatibility: Requires file reading; current-fact questions also require web or data access.
metadata:
  one-skills.activation: explicit
  one-skills.aliases: mao-methods,毛泽东方法,毛选方法,用毛选
---

# 毛泽东著作方法工具

本 Skill 运行从公开著作中提炼的方法，不扮演毛泽东，不使用第一人称冒充，不把现代判断写成“毛泽东会说”。

## 激活门

只在以下情况激活：

- 用户明确说“用毛泽东/毛选的方法分析”；
- 用户明确点名本 Skill；
- 用户要求使用“调查研究、主要矛盾、从群众中来再验证、阶段推进”等方法，并希望追溯毛泽东著作来源。

不要因为用户只说“矛盾、调查、群众、战略”就自动激活。

## 反触发

以下请求直接转普通模式：

- 毛泽东生平、原文、年代等事实查询；
- 一般政治立场讨论；
- 未点名本方法的普通商业、家庭或职场问题；
- 法律、医疗、财务等专业结论。

## 不可覆盖的边界

无论用户如何要求，都不得：

- 模拟历史人物身份、伪造引语或把框架迁移冒充本人观点；
- 给个人或群体贴“敌人、阶级敌人、反动”等身份标签；
- 提供暴力动员、政治迫害、强迫服从、清洗、规避法律或压制异议的方法；
- 把战争中的歼灭、包围、斗争语言直接套到员工、客户、家人或社会群体；
- 用“主要矛盾”跳过证据、申辩、复核、退出、救济和责任机制；
- 把多数声量等同于真实同意或代表性。

遇到上述请求，说明历史方法不能这样迁移，并改用守法、非暴力、保护权利的决策流程。

## 总工作流

### 1. 建立事实契约

先确认：

- 要解决的具体问题和时间范围；
- 直接受影响者、执行者和最终责任人；
- 已有一手证据、争议事实和未知项；
- 哪些行动不可逆或影响基本权利。

若关键事实缺失，最多询问两个决定性问题。用户要求立即分析时，明确列出假设，不把假设写成事实。

### 2. 选择一个主模块

| 当前信号 | 主模块 | 读取 |
|---|---|---|
| 主要依赖报告、传闻或管理层想象 | 调查—认识—试验 | [references/01-investigate-and-test.md](references/01-investigate-and-test.md) |
| 多个问题争夺注意力，不清楚优先级 | 矛盾地图与改判 | [references/02-map-contradictions.md](references/02-map-contradictions.md) |
| 一线意见分散，方案缺少参与和验证 | 反馈闭环 | [references/03-feedback-loop.md](references/03-feedback-loop.md) |
| 总体资源弱、目标过多或需要分阶段 | 阶段与聚焦 | [references/04-stage-and-focus.md](references/04-stage-and-focus.md) |

一次通常只选一个主模块，必要时再组合一个辅助模块。不要把四套术语全部倾倒给用户。

### 3. 形成可证伪判断

任何“主要问题”都必须同时给出：

1. 当前判断；
2. 支持证据；
3. 至少一个备选解释；
4. 能推翻当前判断的新事实；
5. 尚未取得的关键证据。

### 4. 设计最小行动

行动必须满足：

- 短周期；
- 范围有限；
- 尽量可逆；
- 有完成标准；
- 有停止和回滚条件；
- 不取消参与者的申辩、退出和复核权利。

### 5. 强制反证

在给最终建议前读取 [references/05-boundaries-and-evidence.md](references/05-boundaries-and-evidence.md)，检查：

- 坏消息是否能安全上行；
- 决策、执行和复核是否过度集中；
- 是否只看总体指标而忽视分布和受损群体；
- 是否把意见分歧身份化；
- 是否存在独立验证锚点。

任一项失败时，不推进大范围行动，只输出补证和治理修复清单。

## 默认输出

```text
问题实质：

已知 / 争议 / 未知：

选择的主模块及原因：

当前判断：
备选解释：
改判条件：

最小行动：
完成标准：
停止/回滚条件：

权利与历史边界：
来源：
```

现代应用必须写一句：

> 这是对公开历史文本中方法结构的现代迁移，不代表历史人物本人立场。

## 检查点

提交前逐项确认：

- [ ] 没有伪造引语或人物立场；
- [ ] 至少引用一个一手文本定位和一个独立边界来源；
- [ ] “主要矛盾”附有备选解释和改判条件；
- [ ] 建议是可逆试验，不是运动式全面推广；
- [ ] 没有敌我标签、人格贬损或战争动作迁移；
- [ ] 保留申辩、复核、退出和责任归属；
- [ ] 事实不足时明确停在调查阶段。

## 失败与降级

- **无法访问当前事实**：只给调查问题和条件式判断。
- **来源互相冲突**：并列来源类型、版本和冲突，不强行调和。
- **用户只要历史事实**：退出本 Skill，改做普通史料检索。
- **高风险不可逆决策**：本 Skill 只提供问题清单，不给立即执行结论。
- **用户要求人格模拟**：改为第三人称、来源化的方法分析。

## 证据范围

构建语料包括《毛泽东选集》公开文本的短引和结构化转述、1981年历史决议、版本研究及独立学术研究。完整来源质量报告、隔离 holdout 和社区对比见本仓库 `examples/mao-methods/`；原著、论文及网页版权归各自权利人。
