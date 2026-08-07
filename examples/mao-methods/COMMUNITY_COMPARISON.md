# GitHub 毛泽东类 Skills 对比审计

审计日期：2026-08-07。对比目标不是按 Star 排名，而是寻找可迁移的设计并识别事实、路由和安全风险。

冻结版本：`qiushi-skill@6710791`、`maoxuan-skill@cb6c19d`、
`mao-selected-works-skill@5058fe4`、`chinapathbreaker/mao-skill@0c127bd`、
`fyfyfy9314-stack/mao-zedong-perspective-skill@235b538`、
`DDC3344/mao-zedong-perspective@99ba163`。

## 样本

| 项目 | 形态 | 优点 | 主要缺口 |
|---|---|---|---|
| [HughYau/qiushi-skill](https://github.com/HughYau/qiushi-skill) | 1个入口 + 9个方法 + workflows | 跨 Runtime 安装、原文支撑文件、方法分层、可组合工作流、工程完成度高 | 更像方法合集，不是证据化人物研究；缺少独立 holdout、来源集合质量门和逐 Claim 血缘 |
| [leezythu/maoxuan-skill](https://github.com/leezythu/maoxuan-skill) | 单体人物 perspective | 7个模型、外挂全文知识库、安装简单、现代使用示例丰富 | 默认第一人称冒充；超过渐进披露预算；部分现代影响断言缺直接证据；1949年后失败被放入宽泛边界而非运行硬门 |
| [kangarooking/mao-selected-works-skill](https://github.com/kangarooking/mao-selected-works-skill) | 25个原子 Skills | RIA++、候选与 rejected 审计、逐 Skill 诱饵测试、依赖图和学习顺序完整 | 25个相近 Skills 容易互相遮蔽；若干战争方法直接商品化；文本来源只写“1-5卷”，缺版次、独立反证和 Claim 级定位 |
| [chinapathbreaker/mao-skill](https://github.com/chinapathbreaker/mao-skill) | 18个原子 Skills + Darwin 分数 | 有多轮测试记录、关系图和演进结果，体现真实回炉 | “阶级/敌友/歼灭”等模块容易误迁移到日常组织；历史来源含非标准卷本；绝对分数不能证明外部任务效用 |
| [fyfyfy9314-stack/mao-zedong-perspective-skill](https://github.com/fyfyfy9314-stack/mao-zedong-perspective-skill) | 深度人物 perspective | 当前样本中来源和历史边界最完整；包含版本学、外部学术研究、失败史、权利护栏和非冒充规则 | 单文件仍接近500行；人物、方法、史实检索共用一个激活面；静态质量脚本依赖关键词计数，一手占比和模型局限不能由正则可靠证明 |
| [DDC3344/mao-zedong-perspective](https://github.com/DDC3344/mao-zedong-perspective) | 轻量单体人物 Skill | 6个模型、案例、测试提示和文章索引，易读 | 默认第一人称；主要止于1-4卷，缺少建国后失效证据；“不评价政治”会删除验证方法边界所需的历史反例 |

## one-skills 版本的取舍

### 继承

- 从 `qiushi-skill` 继承一个清晰入口和方法路由。
- 从 `cangjie-skill` 继承原子化、反触发、兄弟混淆测试和学习依赖。
- 从 `nuwa-skill` 及 fyfyfy 实例继承版本警告、外部评价、内在张力和诚实边界。
- 从 Darwin/SkillHone 思路继承冻结测试、回滚和保留失败决策历史。

### 不继承

- 不使用第一人称或“同志”等角色扮演表面特征。
- 不把阶级分析、敌友划分、歼灭战、群众运动做成日常组织执行模块。
- 不以“原文出现两次”冒充独立来源验证。
- 不以 Star、文件数量、自动正则分或 LLM 自评宣称质量。
- 不把构建阶段使用过的材料再当独立测试答案。

## v0.3 为什么使用双层网络

`mao-methods` 对 Runtime 只暴露一个显式入口，内部有 12 个分级节点：

1. `verified core`：分布检查、一线反馈完整性、异议与坏消息保护；
2. `supporting principle`：调查、实践检验、反教条、关系地图、阶段改判、阶段试点、中心任务协调；
3. `governance gate`：版本归属纪律、现代迁移权利边界。

严格 Judge 只把 3 个节点认定为同时具备 V1/V2/V3 的独特核心能力；7 个候选因
V3 差异化不足而降级，2 个规范性治理节点不要求经验预测力。系统没有为了对齐
Cangjie 的文件数量把 12 个节点都宣称为独立创新能力。所有节点有 Capability JSON、
文档、测试、证据和先修关系，但不参与全局自动召回。

## 证明协议

- 来源、Object Overview、Portfolio、Capability Graph 和测试集分别冻结 Hash；
- 60 题由同一 Answer Model 在 no-skill、Cangjie 和 one-skills 三个匿名条件下回答；
- Judge 不读取条件映射，只读取 rubric 和匿名回答；
- safety、引用、反触发、sibling、Hash 与 holdout 隔离是不可补偿硬门；
- 最终结果见 `packs/mao-methods/evaluations/comparison-report.json`，未通过时 Pack
  必须停在 test，不能用静态分声称发布。

## 最终同题结果

| 条件 | 综合分 | 任务效果 | 路由 | 证据 | 安全 | 学习 | 成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| no-skill | 75.9048 | 39.5833 | 6.8182 | 5.2992 | 15.0000 | 4.2042 | 5.0000 |
| Cangjie `0c127bd` | 77.0797 | 33.3333 | 13.6364 | 5.3600 | 15.0000 | 4.7500 | 5.0000 |
| one-skills v0.3 | **99.7950** | **50.0000** | **15.0000** | **9.8908** | **15.0000** | **4.9042** | **5.0000** |

one-skills 领先冻结 Cangjie 基线 `22.7153`，超过预设 `5.0` 门槛。60 题分布为：
任务 18、sibling 12、反触发 10、安全 8、引用 6、holdout 6，全部通过。
10 项不可补偿硬门全部为 true，Pack 因此完成 release 并进入 `evolve`。

该结论只适用于冻结 suite、来源集、Skill Hash 与隔离模型会话，不把一次比较外推为
对所有任务、模型或未来版本的永久优势。
