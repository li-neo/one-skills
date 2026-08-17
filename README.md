# one-skills

> 将人、知识、方法、流程与既有 Skill，蒸馏为可运行、可验证、可追溯、可进化的 Agent Skills。

`one-skills` 是一个面向“能力复制”的通用蒸馏框架。

它不把蒸馏理解为摘要、模仿或提示词改写，而是把一个对象中稳定、可迁移的知识与能力，转换为 Agent 可以在真实场景中调用的执行系统：

- 蒸馏人：提取思维模型、决策启发式、表达 DNA、价值边界与行为模式
- 蒸馏内容：从书籍、课程、访谈、播客、文档中提取方法论、框架与原则
- 蒸馏方法论：把抽象理论转换为触发条件、执行步骤、检查点和判停标准
- 蒸馏 SOP：把隐性经验和操作记录转换为可重复执行、可异常恢复的流程
- 蒸馏 Skill：分析现有 Skill 或需求文档，生成、修复或重构为可运行的 Agent Skill
- 蒸馏混合对象：将人物、资料、案例、工具与组织约束组合成一套完整能力包
- 持续进化：通过测试集、独立评审、回归验证和 Darwin 棘轮持续优化

`one-skills` 的目标不是“蒸馏万物”这句口号本身，而是建立一套足够通用、又不会牺牲证据与质量的工程协议。

> **核心判断：复制的不是材料，而是材料背后可被重新运行的能力。**

---

## 项目状态

当前版本 **1.0.0**。Stable Core 已进入工程落地阶段：本地 CLI、Pack 1.0、SQLite 工作区、来源与证据、Overview/Portfolio/Compiler、评测门、迁移、安装和导出按 1.x 兼容策略维护。

HTTP API、Worker、PostgreSQL、S3、插件信任、自动进化及七类 Profile 的通用效果声明仍为 **Experimental**。完整稳定边界与弃用策略见 [Stability and Compatibility](docs/STABILITY.md)。

| 能力 | 状态 |
|---|---|
| 总体架构 | 已实现核心分层 |
| 统一蒸馏协议 | 已实现十阶段状态机与统一 IR |
| 对象 Profile | 七类均有专属 Overview、extractor views、compiler 和 evaluation contract |
| 质量与评测体系 | 已实现 no-skill / baseline / candidate 完整回答盲测、综合分与不可补偿硬门 |
| Darwin 兼容层 | 已实现 `prepared` 交接与降级契约 |
| 工程架构与知识库索引 | [已实现本地 MVP](docs/ARCHITECTURE.md) |
| 根目录 `SKILL.md` | 已完成运行协议 |
| CLI、脚本与 Schema | Stable Core 1.0 |
| 端到端工程链 | 原子提交、恢复、迁移和制品测试覆盖 |
| 示例库 | 已实现单任务、批量并发与七类 Profile 基准 |
| Guided 蒸馏 | 已实现可恢复会话、证据分级、Overview/Portfolio 两次语义确认与无损入 Pack |
| 高质量来源 | 已实现 Local/GitHub/Hugging Face/Manifest 候选发现、Source Catalog、集合质量门、反证和 holdout |
| Skill 召回 | 已实现字段感知 sparse/dense 召回、margin 与拒答 |
| 学习模式 | 已实现先修路径、掌握证据和间隔复习状态 |
| 经验进化 | 已实现 append-only 反馈、复现门、结构化 whole-folder patch、before/after 和 keep/revert |
| 自动化测试 | 62 项，持续扩充 |

Mao 案例保留冻结的 60 题开发比较，但历史 Answer/Judge 为共享模型、会话隔离。Stable 发布门不会把它当作独立质量证明；必须以 Provider 隔离或不同模型重跑后，才能发布为 Stable Pack。

当前可运行命令以 `python3 scripts/one.py --help` 或安装后的 `one --help` 为准。README 中尚未出现在 CLI 帮助里的命令仍属于规划接口。

工程实现、技术文档保存、混合检索、增量索引和三类持续优化闭环详见 [工程架构](docs/ARCHITECTURE.md)。

2026 年 Agent Skills、Skill Retrieval、RAG/Memory、深度研究来源质量、学习路径和持续经验学习的完整复审见 [2026 架构审计](docs/RESEARCH_2026_ARCHITECTURE_AUDIT.md)。

---

## 一句话理解

普通摘要回答：

> “这里讲了什么？”

one-skills 回答：

> “这里有什么能力值得复制？证据是什么？什么时候调用？如何执行？在哪里失效？怎样证明它真的有效？以后如何继续进化？”

---

## 为什么需要 one-skills

现有知识处理方式通常停在四个层次：

1. **收藏**：内容被保存，但无法调用
2. **摘要**：信息被压缩，但没有行动协议
3. **提示词**：有指令，但缺少证据、边界和测试
4. **角色扮演**：表达相似，但判断方式未必真实

一个真正可用的 Skill 至少还需要：

- 明确的触发条件与反触发条件
- 可执行步骤、输入输出和完成标准
- 来源证据、推断链和置信度
- 失败模式、边界、风险和降级路径
- 正例、反例、边界例与回归测试
- 与相邻 Skills 的路由关系
- 可持续更新和可回滚的版本机制

one-skills 把这些要求统一到一条蒸馏流水线中。

---

## 参考项目与继承关系

one-skills 深入参考以下项目，但不会把三套流程机械拼接：

| 项目 | 核心贡献 | one-skills 继承 | one-skills 扩展 |
|---|---|---|---|
| [neo-skills](https://github.com/li-neo/neo-skills) | 轻量蒸馏协议、IR/Lineage/Recipe 与 Guided Controller | 十阶段状态机、强 Schema、测试冻结、对话式材料发现 | 跨 Pack 知识库、ACL、时序记忆、模型提取，以及会话证据等级无损入库 |
| [nuwa-skill](https://github.com/alchaincyf/nuwa-skill) | 蒸馏人的思维方式与表达 DNA | 多源采集、心智模型、决策启发式、表达 DNA、诚实边界、保真度评测 | 私人对象授权、组织角色、能力与人格解耦、隐私分级 |
| [cangjie-skill](https://github.com/kangarooking/cangjie-skill) | 蒸馏长内容中的方法论 | 整体理解、并行提取、三重验证、原子化、触发设计、压力测试 | 从“书”扩展到文档、SOP、案例库、混合语料和既有 Skill |
| [darwin-skill](https://github.com/alchaincyf/darwin-skill) | 进化任意 Skill | 独立评审、效果测试、paired 比较、棘轮、人在回路、可回滚 | 在产物层提供标准适配器，直接调用 Darwin，不重复实现优化器 |

本设计研究时对应的参考版本：

| 项目 | Commit |
|---|---|
| neo-skills | `d88f6db02691dd8dbadeebdb1d6bb247af59dd38`（v0.2.8） |
| cangjie-skill | `55e4b7059c423534f94cfbdeb0a4ee34f3ba6182` |
| nuwa-skill | `27642f5bfed2dc1bbf8ee59a2c1ee602a626bbd7` |
| darwin-skill | `2fbaf4171e453d5c66fc8109a296ae89c4772bc3` |

### 不是简单合并

三类对象有不同的真实性标准：

- 人物 Skill 关心“像不像、判断是否一致、是否诚实标注推断”
- 方法论 Skill 关心“能不能解决新问题、步骤能否执行、边界是否清楚”
- SOP Skill 关心“能不能稳定复现、异常时能否恢复、是否满足完成标准”
- 既有 Skill 关心“触发是否准确、实际效果是否优于 baseline、修改后是否退化”

因此 one-skills 使用统一内核，但为不同对象装配不同的采集器、提取器、构建器和评测器。

---

## 核心设计原则

### 1. 能力优先，而非内容优先

蒸馏的最小单位不是段落或章节，而是一个可迁移的“能力单元”。

一个能力单元必须回答：

- 它解决什么问题？
- 什么信号出现时应调用？
- 调用后具体做什么？
- 结果如何验收？
- 什么情况下不应调用？

### 2. 证据与推断分离

所有重要结论必须标记来源类型：

| 类型 | 含义 |
|---|---|
| `observed` | 原始材料直接陈述或行为直接显示 |
| `corroborated` | 多个独立来源交叉支持 |
| `derived` | 从证据结构化推导 |
| `hypothesized` | 信息不足时的待验证假设 |
| `user_asserted` | 用户提供但尚未独立核实 |

系统不能把“像是这样”写成“事实就是这样”。

### 3. 原子化，但不碎片化

一个 Skill 只承载一个清晰能力，但同一能力所需的上下文、案例、边界和失败恢复必须完整。

判断标准不是文件短，而是职责单一。

### 4. Trigger 是产品接口

Skill 是否有价值，首先取决于：

- 该调用时能否被调用
- 不该调用时能否保持沉默
- 与相邻 Skill 冲突时能否正确路由

因此触发测试不是附属测试，而是出厂门禁。

### 5. 先整体理解，再局部提取

直接逐段抽取容易丢失：

- 全局论点
- 时间演化
- 上下文条件
- 内部矛盾
- 例外和反例

任何复杂对象都必须先建立全局地图，再并行提取能力单元。

### 6. 保留矛盾，不制造虚假统一

人的观点会演化，方法论会受情境约束，SOP 会存在例外。

系统应区分：

- 时间性变化
- 场景性差异
- 价值张力
- 来源冲突
- 未解决问题

矛盾本身可能是高价值知识。

### 7. 评测者与构建者分离

生成者不能独自证明自己生成得好。

关键评测采用：

- 独立答题 Agent
- 独立评分 Agent
- 隐藏预期答案的盲测
- 改前与改后的 paired 比较
- 必要时人工复核

### 8. 人在回路，但不把确认变成阻塞

只在高成本或高主观性的节点确认：

- 蒸馏目标与授权范围
- 全局理解和能力候选
- 最终验收标准
- 高风险发布或进化变更

可使用合理默认值的地方直接推进。

### 9. 产物必须自包含

一个发布后的 Skill 应能独立复制、安装和审计，不依赖作者机器上的隐式路径。

### 10. 只保留可验证的进步

任何进化都必须有：

- 改前基线
- 明确假设
- 单变量或可归因的修改
- 回归测试
- keep / revert 决策

---

## 支持的蒸馏对象

### 对象类型

| Profile | 输入示例 | 核心产物 | 主要验收标准 |
|---|---|---|---|
| `person` | 自己、家人、同事、老板、名人、历史人物 | 思维与决策 Skill | 保真度、诚实度、来源透明度 |
| `content` | 书、课程、播客、访谈、长文、视频字幕 | 方法论 Skill Pack | 生成力、独特性、可调用性 |
| `methodology` | 理论、框架、原则、模型 | 执行型 Skill | 场景迁移、步骤完整、边界明确 |
| `sop` | 操作手册、录屏、聊天记录、工单、流程文档 | SOP Skill | 可复现、异常恢复、完成标准 |
| `skill` | 现有 `SKILL.md`、需求文档、散乱提示词 | 可运行 Skill | Trigger、实际效果、结构质量 |
| `hybrid` | 人物 + 文档 + 案例 + 工具 | 复合能力包 | 路由正确、组件协同、端到端效果 |
| `auto` | 未明确分类的任意输入 | 分类建议或组合 Profile | 分类置信度与用户目标匹配 |

### “蒸馏万物”的真实含义

one-skills 并不假设所有对象都能被完整复制。

可以被蒸馏的是：

- 有证据支撑的知识
- 可观察的决策模式
- 可表达的判断规则
- 可重复的操作流程
- 可测试的技能表现

不能被可靠蒸馏的是：

- 未被表达或观察到的直觉
- 只存在于身体经验中的技能
- 私人未授权信息
- 缺少样本却被要求确定复刻的性格
- 无法定义成功标准的“感觉”

---

## 总体架构

```text
                         ┌──────────────────────────┐
                         │      Distillation Goal   │
                         │  对象 / 用途 / 边界 / 验收  │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │     Router & Planner     │
                         │ 分类 Profile / 选择档位 / 计划 │
                         └────────────┬─────────────┘
                                      │
           ┌──────────────────────────▼──────────────────────────┐
           │                Distillation Kernel                  │
           │ ingest → evidence → extract → verify → synthesize  │
           └───────────────┬───────────────────┬─────────────────┘
                           │                   │
              ┌────────────▼──────────┐  ┌────▼─────────────────┐
              │ Profile Components   │  │ Universal IR         │
              │ person/content/sop…  │  │ 证据、能力、触发、边界   │
              └────────────┬──────────┘  └────┬─────────────────┘
                           │                   │
                    ┌──────▼───────────────────▼──────┐
                    │       Skill Pack Builder        │
                    │ SKILL / references / evals / manifest │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │      Validation Harness         │
                    │ static / routing / behavior / safety │
                    └──────────────┬──────────────────┘
                                   │
                  ┌────────────────▼─────────────────┐
                  │ Delivery & Evolution Adapters    │
                  │ runtime install / Darwin / report │
                  └──────────────────────────────────┘
```

### 五层架构

#### 1. Intake Layer

负责接受文件、目录、URL、对话、录屏转写、现有 Skill 或自然语言需求，并建立输入清单。

#### 2. Evidence Layer

负责来源登记、切块、去重、可信度、引用定位、冲突记录和授权边界。

#### 3. Distillation Kernel

负责候选提取、跨源验证、能力建模、原子化、关系构图与统一中间表示。

#### 4. Profile Layer

按对象类型装配专用组件：

- collectors：采集什么
- extractors：提取什么
- builders：如何组织
- evaluators：如何证明有效

#### 5. Delivery & Evolution Layer

负责输出 Agent Skill、安装、生成报告、接入 Darwin、做版本和回滚。

---

## 统一中间表示：One Distillation IR

one-skills 的关键不是统一最终模板，而是统一中间表示。

不同对象都先被转换为 `Distillation IR`，再由 Profile 构建不同产物。

```yaml
object:
  id: karpathy
  type: person
  goal: "用于 AI 工程决策与教学表达"
  scope: "公开资料，截至 2026-07"
  consent: public

sources:
  - id: src-001
    kind: interview
    uri: "..."
    author: "..."
    captured_at: "2026-08-04"
    authority: primary
    license: unknown
    access: public

claims:
  - id: claim-001
    statement: "..."
    status: corroborated
    confidence: 0.91
    evidence: [src-001#t=10:23, src-004#p=18]
    contradictions: [claim-009]

capabilities:
  - id: capability-001
    name: "从约束出发拆解 AI 产品"
    problem: "..."
    triggers: ["...", "..."]
    anti_triggers: ["..."]
    inputs: ["..."]
    procedure:
      - step: "..."
        done_when: "..."
    outputs: ["..."]
    boundaries: ["..."]
    failure_modes: ["..."]
    evidence: [claim-001, claim-007]

style:
  enabled: true
  traits: ["短句", "技术类比"]
  forbidden_patterns: ["空泛鸡汤"]

evals:
  - id: route-positive-001
    type: should_trigger
    prompt: "..."
    expected: "..."
    covers: [capability-001]
```

### IR 的价值

- 同一证据可以支持多种产物
- 同一能力可以用不同表达模板发布
- 人物表达与人物能力可以解耦
- Profile 可以独立演进
- 评测不依赖某个固定 README 或 SKILL 模板
- 可以生成 Darwin、其他 Runtime 或未来协议所需的适配格式

---

## 通用蒸馏流水线

```text
Phase 0  Contract     定义对象、用途、授权、档位、验收
Phase 1  Ingest       采集、解析、清洗、分块、建立来源账本
Phase 2  Map          建立对象全局地图与信息缺口
Phase 3  Extract      多视角并行提取候选能力
Phase 4  Verify       证据交叉验证、去常识、测生成力
Phase 5  Model        构建 Distillation IR 与能力关系图
Phase 6  Build        生成 Skill Pack
Phase 7  Validate     静态、路由、行为、保真、安全测试
Phase 8  Deliver      安装、报告、版本、发布
Phase 9  Evolve       Darwin 优化与新证据增量更新
```

### Phase 0：蒸馏契约

开始前定义：

- **对象**：蒸馏谁或什么
- **用途**：决策顾问、执行助手、培训、知识复用或 Skill 发布
- **受众**：自己、团队、公众或特定岗位
- **范围**：全面蒸馏还是聚焦某个能力
- **证据范围**：仅用户材料、允许联网补充、仅公开一手来源
- **授权范围**：公开、本人授权、组织内部、敏感受限
- **交付形式**：单 Skill、Skill Pack、SOP、方法论库
- **验收标准**：哪些任务成功才算蒸馏有效
- **档位**：快速、标准、深度

输出：`DISTILLATION_CONTRACT.md`

### Phase 1：采集与证据账本

所有输入写入 `sources/manifest.yaml`：

- 文件哈希与采集时间
- 作者、时间、出处和定位信息
- 一手、二手或用户陈述
- 许可证和可发布范围
- 隐私等级
- 是否允许进入最终 Skill

原始材料不直接混入结论。系统先建立可追溯证据层。

### Phase 2：全局地图

按 Profile 生成对象地图：

- 人物：时间线、领域、关键决策、观点演化、表达场景
- 内容：主旨、结构、概念、论证链、案例和反例
- 方法论：目标、假设、机制、步骤、适用边界
- SOP：角色、前置条件、系统、状态、异常和交接点
- Skill：承诺能力、触发器、工作流、资源、测试和已知问题

输出：`OBJECT_OVERVIEW.json`；`OBJECT_OVERVIEW.md` 只是人类可读投影。

### Phase 3：多视角提取

通用提取器：

| 提取器 | 寻找内容 |
|---|---|
| capability | 可迁移能力与问题解决模式 |
| framework | 决策框架、模型和原则 |
| procedure | 操作步骤、输入输出、判停条件 |
| trigger | 使用场景、语言信号、前置状态 |
| counterexample | 失败案例、反模式、误用条件 |
| boundary | 适用范围、风险、时代和样本限制 |
| vocabulary | 术语、定义和概念关系 |
| evidence | 关键原文、行为、案例和定位信息 |

Profile 可追加专用提取器，例如人物的 `expression-dna`、SOP 的 `exception-path`。

### Phase 4：验证与筛选

候选能力默认执行六项验证：

| Gate | 问题 |
|---|---|
| Evidence | 是否有可定位证据？ |
| Recurrence | 是否跨来源、跨场景或跨时间复现？ |
| Generativity | 能否处理原材料没有直接回答的新问题？ |
| Distinctiveness | 是否超越常识或通用 AI 建议？ |
| Executability | 能否转化为 Agent 可执行步骤？ |
| Boundary | 是否知道何时不适用？ |

验证结果：

- `accepted`：进入能力模型
- `downgraded`：降级为启发式、背景或案例
- `rejected`：保留原因，不进入成品
- `needs_evidence`：进入补充采集队列

### Phase 5：能力建模

每个能力单元形成完整契约：

```text
Problem → Trigger → Input → Procedure → Output → Done
                       ↓
               Boundary / Failure / Fallback
                       ↓
                  Evidence / Confidence
```

同时建立关系图：

- `depends_on`
- `contrasts_with`
- `composes_with`
- `supersedes`
- `conflicts_with`
- `routes_to`

### Phase 6：构建 Skill Pack

构建器根据 Profile 选择模板，而不是把所有信息塞进一个巨大 `SKILL.md`。

构建原则：

- 高频执行规则放入 `SKILL.md`
- 详细证据放入 `references/`
- 可重复工具放入 `scripts/`
- 测试放入 `evals/`
- 来源和版本放入 `manifest.yaml`
- 大型对象拆成多个原子 Skill，并提供路由索引

### Phase 7：验证

测试顺序：

1. Schema 与静态检查
2. Trigger 正例、反例和边界例
3. 相邻 Skill 混淆测试
4. 端到端行为测试
5. Profile 专项测试
6. 安全、隐私和来源检查
7. 独立评分与人工抽检

任何高风险测试失败都阻止发布。

### Phase 8：交付

交付不等于生成文件，还包括：

- 安装到目标 Runtime
- 验证 Runtime 能发现并触发 Skill
- 输出质量报告和已知限制
- 固化版本号和来源截止时间
- 生成可复跑测试集

### Phase 9：进化

进化分成两条独立通道：

#### 内容进化

新资料、新行为、新版本或新案例进入后：

1. 只处理增量来源
2. 判断强化、冲突、替代或新增
3. 更新 IR 和受影响能力
4. 运行受影响测试与全局回归

#### Skill 进化

直接调用 Darwin：

1. 将 one-skills canonical evals 适配为 Darwin 测试格式
2. 建立 git 基线
3. 由 Darwin 做结构与效果评估
4. paired 独立评审改前与改后
5. 只保留多数评审确认的改进
6. 人工确认高风险变更

---

## Profile 设计

### Person Profile：蒸馏人

#### 蒸馏维度

- 反复出现的心智模型
- 决策启发式
- 价值排序与反模式
- 重大决策与实际行为
- 表达 DNA
- 时间演化
- 内在张力
- 智识谱系
- 诚实边界

#### 能力与表达解耦

人物 Skill 支持三种运行模式：

| 模式 | 行为 |
|---|---|
| `advisor` | 使用其框架分析，但不模仿身份 |
| `perspective` | 明确以“某人的视角”给出推断 |
| `voice` | 在授权和低风险场景中应用表达 DNA |

默认使用 `advisor`，避免把能力复制退化成角色模仿。

#### 人物专项评测

- 已知立场一致性
- 新问题生成力
- 表达辨识度
- 未知问题的边缘诚实度
- 行为与言论冲突处理
- 一手来源占比
- 截止日期与时效性

#### 自己、家人、同事和老板

私人对象不能照搬名人公开资料流程。

必须先建立授权：

| 等级 | 允许范围 |
|---|---|
| `self` | 用户本人提供的材料和访谈 |
| `consented` | 对方明确同意的材料与用途 |
| `work-authorized` | 组织授权的工作知识，限制内部使用 |
| `public-only` | 仅使用公开信息，不推断私密特征 |
| `prohibited` | 未授权私聊、秘密录音、敏感个人数据 |

涉及同事或老板时，优先蒸馏“岗位能力”和“工作方法”，而不是建立未经同意的人格复制品。

### Content Profile：蒸馏书与长内容

继承整体理解、并行提取、三重验证和原子化原则。

核心产物：

- 内容地图
- 方法论候选池
- 接受与淘汰记录
- 原子 Skills
- 术语表
- Skill 关系图
- 面向人的 Digest

内容摘要可以是副产物，但不能替代 Skill。

### Methodology Profile：蒸馏方法论

方法论必须被转换为：

- 目标问题
- 成立假设
- 核心机制
- 诊断问题
- 执行步骤
- 决策分支
- 产出格式
- 完成标准
- 失效条件
- 误用案例

如果一个理论不能形成可测试的执行变化，它只能被发布为知识参考，不能伪装成执行 Skill。

### SOP Profile：蒸馏流程

SOP 的最小模型：

```text
Role + Preconditions + Inputs + Systems
  → Steps + Checkpoints + Handoffs
  → Outputs + Done Criteria
  → Exceptions + Rollback + Escalation
```

SOP 专项要求：

- 每一步有负责人或执行主体
- 每一步有输入和输出
- 跨系统操作形成完整闭环
- 异常分支不依赖隐性常识
- 高风险动作有确认和回滚
- 删除、迁移、发布等操作覆盖所有关联系统

### Skill Profile：创建或蒸馏既有 Skill

支持三种输入：

- 现有 `SKILL.md`
- 描述期望能力的文档
- 零散提示词、案例和期望输出

处理模式：

| 模式 | 目的 |
|---|---|
| `create` | 从需求和证据创建新 Skill |
| `extract` | 从复杂材料中抽出一个或多个 Skills |
| `repair` | 修复触发、工作流、边界或测试 |
| `refactor` | 在不改变核心能力的前提下重构 |
| `evaluate` | 只评测，不修改 |

### Hybrid Profile：复合能力

示例：

> 用某位销售负责人的历史复盘、团队 SOP、客户案例和 CRM 操作手册，蒸馏一套企业销售 Skill Pack。

Hybrid Profile 不是把所有内容写入一个文件，而是生成：

- 能力路由器
- 人物判断模块
- 方法论模块
- SOP 执行模块
- 工具适配模块
- 共享证据与测试

---

## 质量体系

### 通用质量门禁

| 维度 | 权重建议 | 核心问题 |
|---|---:|---|
| 证据可追溯性 | 15 | 关键结论能否定位到来源？ |
| 触发准确性 | 15 | 应调用与不应调用是否分明？ |
| 可执行性 | 15 | Agent 能否按步骤完成任务？ |
| 实际效果 | 20 | 是否显著优于无 Skill baseline？ |
| 边界与失败恢复 | 10 | 是否编码失效、异常和 fallback？ |
| 独特性与信息增益 | 10 | 是否只是通用常识？ |
| 结构与资源完整性 | 5 | 文件、引用、脚本是否完整？ |
| 安全、隐私与授权 | 10 | 是否满足发布和使用边界？ |

权重不是全局固定常量。Profile 可以调整，但必须在蒸馏契约中冻结，不能为了让结果通过而事后改分。

### 测试集结构

```json
{
  "schema_version": "1.0",
  "skill": "example-skill",
  "cases": [
    {
      "id": "route-positive-001",
      "type": "should_trigger",
      "prompt": "用户的真实表达",
      "expected": "应触发并执行指定动作",
      "covers": ["capability-001"]
    },
    {
      "id": "route-negative-001",
      "type": "should_not_trigger",
      "prompt": "看似相关但不应触发的表达",
      "expected": "保持沉默或路由到其他 Skill"
    },
    {
      "id": "behavior-001",
      "type": "task",
      "prompt": "一个完整任务",
      "expected": "可验证的结果约束"
    }
  ]
}
```

### 必测类型

- `should_trigger`
- `should_not_trigger`
- `edge_case`
- `sibling_conflict`
- `task`
- `failure_recovery`
- `safety`
- `regression`
- Profile 专项测试

### 通过策略

- 安全、隐私和授权：必须 100%
- `should_not_trigger`：默认 100%
- 相邻 Skill 混淆：默认 100%
- 核心任务：达到蒸馏契约约定阈值
- 总分达标但核心任务失败：仍不得发布

### 防止自评自证

推荐执行拓扑：

```text
Builder Agent
    │
    ├── Answer Agent：只读 Skill，执行测试
    │
    ├── Baseline Agent：不读 Skill，执行同一测试
    │
    └── Judge Agents：盲评两组结果
                         │
                         └── Human Review：处理分歧和高风险项
```

---

## Darwin 集成

one-skills 不 fork Darwin，也不重新实现一套优化器。

集成边界：

```text
One canonical evals
        │
        ▼
Darwin Adapter
        │
        ├── test-prompts.json
        ├── baseline metadata
        └── protected constraints
        │
        ▼
darwin-skill
        │
        ├── baseline
        ├── experiment
        ├── paired judges
        ├── keep / revert
        └── report
        │
        ▼
Neo regression gate
```

### 为什么需要适配层

参考项目的 `test-prompts.json` 结构并不完全一致。one-skills 保留自己的规范化测试集，再生成目标 Darwin 版本所需格式，避免核心数据结构被外部版本绑定。

### 受保护约束

Darwin 优化时不得改变：

- 蒸馏对象和核心用途
- 来源事实与引用
- 用户授权边界
- 安全红线
- 关键反触发条件
- Profile 的硬性质量门禁

### 进化日志

每次进化记录：

- 输入版本和输出版本
- 修改假设
- 变更范围
- paired 评审票数
- 回归结果
- keep / revert 决策
- 人工审批人

---

## 产物结构

```text
one-skills/
├── README.md
├── SKILL.md
├── profiles/
│   ├── person/
│   ├── content/
│   ├── methodology/
│   ├── sop/
│   ├── skill/
│   └── hybrid/
├── core/
│   ├── schemas/
│   ├── extractors/
│   ├── validators/
│   └── adapters/
├── templates/
├── scripts/
├── references/
├── evals/
└── examples/
```

单次蒸馏任务实际输出：

```text
packs/<object-slug>/
├── pack.json                 # 契约、生命周期、Recipe 与重现约束真源
├── SOURCE_MANIFEST.json      # 来源版本与 Source Quality 真源
├── OBJECT_OVERVIEW.json      # 对象整体理解真源
├── EVIDENCE_LEDGER.jsonl     # 不可变证据真源
├── VERIFIED_PORTFOLIO.json   # 能力组合真源
├── evaluations/              # 冻结评测真源
│
├── candidates/               # 中间候选，可重建
├── verified/                 # 中间决策，可重建
├── rejected/                 # 拒绝审计，可重建
│
├── DISTILLATION_CONTRACT.md
├── INDEX.md
├── sources/
│   └── chunks.json
├── ir/
│   └── distillation.json
├── skills/
│   └── <skill-slug>/
│       ├── SKILL.md
│       ├── capability.json
│       ├── test-prompts.json
│       ├── agents/
│       ├── references/
│       └── evals/canonical.json
├── reports/
│   ├── QUALITY.md
│   ├── PROVENANCE.md
│   └── EVIDENCE_GRAPH.md
├── audit/
└── evolution/
    ├── darwin-request.json
    └── DARWIN_REQUEST.md
```

---

## 断点续跑

长任务状态写入 `pack.json.lifecycle`，不再维护独立状态文件：

```json
{
  "schema_version": "1.0",
  "lifecycle": {
    "current_phase": "verify",
    "phases": {
      "extract": {"status": "completed"},
      "verify": {"status": "blocked"}
    }
  }
}
```

恢复时先读取状态和产物，不重新消耗已经完成的采集与提取成本。

---

## 蒸馏档位

| 档位 | 适用场景 | 采集与测试 |
|---|---|---|
| 快速 | 概念验证、单文档、内部试用 | 少量核心来源、最小测试集 |
| 标准 | 大多数正式 Skill | 多源验证、完整路由与行为测试 |
| 深度 | 公开发布、关键岗位、复杂人物 | 全量一手资料、双盲评测、完整审计 |

档位改变投入，不改变安全和诚实底线。

---

## 使用方式

要求 Python 3.10+。源码目录可直接运行，也可以执行 `python3 -m pip install -e .` 安装 `one` 命令。

```bash
python3 scripts/one.py init .
python3 scripts/one.py --help
```

### 自动识别对象

```bash
one distill --source ./inputs --type auto --workspace .
```

对象仍不明确时先使用可拒答路由，不猜测：

```bash
one route --intent "把这个人的著作和决策方法做成可运行能力"
```

### 高质量来源目录

```bash
one source discover \
  --adapter github \
  --target owner/repository \
  --subject example \
  --question "这个对象解决什么问题" \
  --output SOURCE_CANDIDATES.json

one source template --output SOURCE_CATALOG.json
one source audit \
  --catalog SOURCE_CATALOG.json \
  --type methodology \
  --mode deep

one distill \
  --workspace . \
  --source-catalog SOURCE_CATALOG.json \
  --type methodology \
  --mode deep \
  --name example
```

来源目录把一手、二手、反证、验证锚点和 `evaluation_only` 分开，完整协议见 [来源质量](docs/SOURCE_QUALITY.md)。

### Skill 召回、学习与反馈

```bash
one skill-search "只看了行业报告，还没访谈用户" \
  --root ./packs/example/skills

one learn init ./packs/example --learner alice
one learn next ./packs/example --learner alice

one experience record ./packs/example \
  --skill example-skill \
  --task-signature "重复出现的失败模式" \
  --outcome failure \
  --result-summary "实际结果摘要" \
  --evidence-locator run:001
one experience mine ./packs/example
```

详见 [学习路径与经验进化](docs/LEARNING_AND_EXPERIENCE.md)。

### 材料不足时启动 Guided Session

Guided Session 不替代正式十阶段 Pipeline。它先通过每轮最多三个问题、证据分级和人工检查点，把模糊目标与对话材料整理成可恢复的输入，再创建正式 Pack。

```bash
one guide init ./guided/reviewer \
  --subject "Decision Method" \
  --object methodology \
  --target-capability "评审产品方案" \
  --target-user "产品团队" \
  --output-goal "Reviewer Skill" \
  --access authorized

one guide advance ./guided/reviewer
one guide confirm ./guided/reviewer --checkpoint scope --status confirmed
one guide advance ./guided/reviewer
one guide confirm ./guided/reviewer \
  --checkpoint evidence_inventory --status confirmed
one guide advance ./guided/reviewer
one guide record ./guided/reviewer \
  --kind answer \
  --content "我会先确认方案承载的决定，再检查不可逆风险。" \
  --evidence-class self_report \
  --permission authorized \
  --locator "conversation:turn-1"
one guide create-pack ./guided/reviewer --output .
# 使用 create-pack 输出的 Pack 路径：
PACK_PATH="<create-pack JSON 输出中的 pack 字段>"
one next "$PACK_PATH"
```

`create-pack` 进入与 `distill` 相同的正式十阶段 Pipeline，其 JSON 输出会给出下一步命令。`self_report`、`scenario_response`、`observed_behavior`、`documented_result` 等等级会原样进入 Pack 的证据账本和知识库，不会在 Markdown 摄取后退化为普通引文。完整协议见 [Guided Distillation](docs/GUIDED_DISTILLATION.md)。

### 蒸馏一个人

```bash
one distill \
  --source ./materials/person \
  --type person \
  --name "Example Person" \
  --mode standard \
  --access authorized \
  --consent self

# 先按输出确认 Object Overview；模型验证前检查实际端点和授权阻塞：
one next ./packs/example-person
one next ./packs/example-person --allow-sensitive-data
```

`--consent self/consented/work-authorized` 只记录蒸馏授权，不自动代表允许向第三方模型发送材料。非公开 Pack 的 `one next` 会列出 Builder、Answer、Judge 的模型与 `base_url`；每次执行 `verify-model` 或 `compare run` 前，只有确认授权范围覆盖这些端点后，才使用 `--allow-sensitive-data` 返回并执行命令。

本地 Ollama、vLLM 等服务可直接使用 OpenAI-compatible 端点：

```bash
export ONE_SKILLS_MODEL_BASE_URL="http://127.0.0.1:11434/v1"
export ONE_SKILLS_MODEL_API_KEY="local"
export ONE_SKILLS_MODEL="qwen3"
one model status
```

回环地址只说明网络目的地在本机，仍需确认该服务不会把请求代理到外部。
单模型 fallback 可用于验证和开发证据；Stable 发布评测仍要求 Answer 与 Judge 达到 Provider 隔离或模型隔离。

### 从文档创建 Skill

```bash
one distill --source ./docs/requirement.md --type skill --mode standard
```

### 蒸馏一本书

```bash
one distill --source ./books/example.pdf --type content --mode deep
```

### 整理 SOP

```bash
one distill \
  --source ./recordings \
  --source ./tickets \
  --source ./manuals \
  --type sop \
  --name "用户离职清理闭环"
```

### 调用 Darwin 进化

```bash
one evolve ./packs/example --skill example-skill
```

### 三角色验证、编译与受控发布

```bash
export ONE_SKILLS_BUILDER_BASE_URL="https://model.example/v1"
export ONE_SKILLS_BUILDER_API_KEY="..."
export ONE_SKILLS_BUILDER_MODEL="builder-model"
# 同样配置 ONE_SKILLS_ANSWER_* 与 ONE_SKILLS_JUDGE_*；
# 只有一套模型时可回退到 ONE_SKILLS_MODEL_*。

one model status
one next ./packs/example
one semantic confirm ./packs/example \
  --artifact overview --notes "对象骨架和来源已核对"
one verify-model ./packs/example
one semantic confirm ./packs/example \
  --artifact portfolio --notes "能力组合和降级理由已核对"
one compile ./packs/example

one compare freeze ./packs/example \
  --suite benchmarks/mao-methods/suite.json
one compare run ./packs/example \
  --suite benchmarks/mao-methods/suite.json \
  --baseline benchmarks/mao-methods/baselines.json
one release ./packs/example
one install ./packs/example --target ~/.codex/skills
one export ./packs/example --runtime claude
```

`one next <pack>` 是只读操作：它综合 lifecycle、semantic contract、验证审计和评测产物返回 `action`、可执行 `command`、`blocked_by`、`warnings` 与模型 `endpoints`，不会推进状态或调用模型。缺少人工确认说明、Suite、baseline 或敏感数据授权时不会伪造命令，可分别通过 `--notes`、`--suite`、`--baseline`、`--allow-sensitive-data` 显式补齐。

非公开 Pack 默认禁止发送到模型端点。只有在确认端点、数据协议和授权范围后，才能显式增加 `--allow-sensitive-data`。比较 Suite 必须在运行前独立冻结；`--baseline` 是必填的冻结对照 Skill 与评分契约清单，不是预跑结果。三角色未配置时可以从隔离 Runtime 导入完整 Answer/Judge artifacts，但未签名的导入结果只作为开发证据，不能通过 Stable 发布门。

`one approve --candidate ...` 是旧版单候选编译旁路，不满足 Stable 1.0 的 Portfolio 确认流程。可发布 Pack 应使用 `verify-model → semantic confirm portfolio → compile`。

### 检索与用户画像记忆

```bash
one search "如何验证删除动作已经闭环" --access authorized
one memory subject --name "Example Person" --relation self
one memory fact --action ADD --subject <subject-id> \
  --dimension preference --statement "偏好结论附带证据" \
  --confidence 0.9

one lineage --type source --id <source-id>
one source-revoke --id <source-id> --reason "来源方撤回授权"

one batch --manifest examples/batch-manifest.json --workers 8

one acl tenant --tenant team-a --name "Team A"
one acl principal --tenant team-a --principal alice --name "Alice"
one acl grant --tenant team-a --principal alice \
  --asset-type chunk --asset-id <chunk-id> --permission read

one job submit --type distill --payload ./job-payload.json
one job worker --owner worker-01

export ONE_SKILLS_API_TOKEN="replace-with-secret"
one serve --host 127.0.0.1 --port 8765
```

---

## 配置示例

```yaml
project:
  name: example-distillation
  profile: person
  depth: standard

goal:
  use_case: "产品决策顾问"
  audience: internal
  output_mode: advisor

sources:
  network: false
  paths:
    - ./materials/interviews
    - ./materials/decision-memos
  minimum_primary_ratio: 0.6

privacy:
  consent: work-authorized
  publish_raw_sources: false
  redact:
    - email
    - phone
    - customer_name

quality:
  minimum_score: 85
  require_negative_tests: true
  require_independent_judges: true
  sibling_conflict_tolerance: 0

evolution:
  engine: darwin
  max_rounds: 3
  human_checkpoint: true
```

---

## 典型场景

### 场景 1：蒸馏自己

输入：

- 过去文章和复盘
- 决策备忘录
- 会议发言
- 项目成败案例
- 他人反馈

输出不是“我的数字分身”，而是：

- 我稳定使用的决策框架
- 我的优势能力与可复用流程
- 我的表达习惯
- 我的盲区和反模式
- 哪些判断有充分证据，哪些只是自我描述

### 场景 2：蒸馏同事或老板

优先目标：

- 减少关键岗位知识流失
- 固化工作判断和交付标准
- 形成团队培训与决策辅助 Skill

禁止目标：

- 未经授权复制私人聊天
- 推断敏感人格或健康信息
- 用 Skill 冒充本人做承诺

### 场景 3：从需求文档创建 Skill

系统先区分：

- 文档描述的是知识、方法、流程还是工具
- 单 Skill 是否足够
- 成功标准能否转成测试
- 哪些信息缺失会导致无法执行

然后构建可运行 Skill，而不是把需求文档原样包进 Markdown。

### 场景 4：蒸馏完整方法论

将理论拆成：

- 诊断模块
- 决策模块
- 执行模块
- 复盘模块

并通过真实案例验证它能否迁移到新问题。

### 场景 5：蒸馏组织 SOP

从文档、工单和操作记录中恢复真实流程，重点识别：

- 文档写法与实际操作的差异
- 依赖个人记忆的隐性步骤
- 跨系统遗漏
- 异常恢复和升级路径

---

## 安全、隐私与伦理

### 基本规则

1. 不将“蒸馏人”宣传为完整复制人格
2. 不把框架推断伪装成本人真实观点
3. 不采集未授权私人信息
4. 不使用秘密录音、泄露聊天记录或非法来源
5. 不输出可用于冒充本人授权、承诺或签署的能力
6. 对在世私人个体默认要求明确授权
7. 支持来源删除、能力重建和派生产物追踪

### 数据分级

| 级别 | 示例 | 默认策略 |
|---|---|---|
| Public | 公开演讲、出版物 | 可引用，仍需记录许可证 |
| Internal | 内部 SOP、工作文档 | 不公开原文，限制安装范围 |
| Confidential | 客户数据、战略材料 | 最小化处理、加密存储、禁止进入公开 Skill |
| Sensitive Personal | 健康、身份、私聊 | 默认拒绝，除非合法且有明确必要性 |

### 被遗忘与撤销

必须能回答：

- 某条结论来自哪些来源？
- 删除某个来源会影响哪些能力？
- 某人撤销授权后需要删除哪些派生产物？

这要求证据图和产物之间保持反向索引。

---

## Runtime 中立

one-skills 面向 Agent Skills 兼容生态，不绑定单一 Runtime。

原则：

- 核心 `SKILL.md` 使用通用能力描述
- Runtime 专属工具通过 Adapter 注入
- 缺少 sub-agent 时可以串行降级
- 缺少网络时可以纯本地语料运行
- 缺少脚本执行能力时保留人工步骤
- 安装路径由目标 Runtime Adapter 决定

---

## 失败模式与降级

| 触发条件 | 一线处理 | 仍失败时 |
|---|---|---|
| 无法判断对象类型 | 给出候选 Profile 和判断依据 | 要求用户选择目标产物 |
| 来源不足 | 缩小能力范围并标低置信度 | 只交付研究缺口，不生成虚假 Skill |
| 来源冲突 | 保留冲突并按时间/场景拆分 | 交由人工裁决 |
| 无并行 Agent | 串行执行提取器并逐步落盘 | 降低档位但不跳过验证 |
| 上下文不足 | 按 Phase 分会话续跑 | 使用 IR 和状态文件恢复 |
| 无法自动测试 | 执行静态与人工测试 | 标记为未通过自动验证 |
| Skill 互相抢触发 | 增加 sibling conflict 测试 | 合并、拆分或引入路由 Skill |
| Darwin 版本格式变化 | 更新 Adapter | 保留 canonical evals，不损失测试资产 |

---

## 反模式黑名单

one-skills 不做以下事情：

1. 没有原始材料却凭模型记忆“蒸馏”
2. 把摘要包装成 Skill
3. 把通用常识包装成独特能力
4. 只测试正例，不测试误触发
5. 同一个 Agent 生成、答题、评分并宣布通过
6. 为提高分数堆叠冗余指令
7. 把人物表达模仿当成思维复制
8. 消除人物和资料中的真实矛盾
9. 修改测试来迁就失败产物
10. 在没有授权时蒸馏私人个体
11. 把规划中的接口描述成已实现功能
12. 为了“通用”制造一个不可维护的巨型 Skill

---

## 路线图

### Milestone 0：设计基线

- [x] 完成参考项目研究
- [x] 定义统一架构
- [x] 定义 Profile 模型
- [x] 定义验证与 Darwin 集成原则
- [x] 完成 Pack、Evidence、Distillation IR、canonical eval 与 Darwin eval Schema

### Milestone 1：最小闭环

- [x] 建立本地 Source Store、不可变文档版本和 SQLite 元数据
- [x] 实现结构化 Chunk、SQLite FTS5 与本地语义索引
- [x] 实现 `content` Profile
- [x] 实现 `skill` Profile
- [x] 建立 canonical eval schema 与 Darwin Adapter
- [x] 输出可运行、可安装、可导出的 Skill
- [x] 完成 Trigger、行为、边界、安全与相邻冲突测试框架

### Milestone 2：人物与 SOP

- [x] 实现 `person` Profile 与时序记忆
- [x] 实现授权等级、模型外发隐私门和撤销数据模型
- [x] 实现 `sop` Profile 与破坏性操作闭环约束
- [x] 建立七类 Profile 专项测试

### Milestone 3：Darwin 与增量更新

- [x] 建立 Recipe Registry 与非补偿式晋升门
- [x] 建立七类 Profile 固定 Benchmark 语料与基准运行器
- [x] 实现 Darwin Adapter
- [x] 接入 paired 评审决策；Git 提交与回滚由 Darwin 执行
- [x] 支持来源增量更新与 active version 原子切换
- [x] 支持来源撤销、影响报告与下游阶段失效
- [x] 支持按血缘自动选择局部回归测试

### Milestone 4：生态化

- [x] 建立本地内容寻址对象存储与可选 S3 Adapter
- [x] 建立多租户召回前 ACL、持久 Worker lease 和 append-only 审计事件
- [x] 完成 PostgreSQL + pgvector 初始化、迁移、ACL 混合检索与负载测试工具
- [x] 在 CI PostgreSQL 16 + pgvector 环境完成迁移、并发写入、重连和容量验证
- [x] Profile entry-point 插件协议
- [x] Generic、Codex、Claude Code、Cursor Runtime Adapters
- [x] 建立可复现端到端示例
- [x] 建立七类 Profile 专项模板导出与示例库
- [x] 批量蒸馏、错误隔离和有界并发执行
- [x] 生成证据索引、质量报告与 Provenance 报告
- [x] 发布时生成 Mermaid 可视化证据图

### Milestone 5：v0.4 核心收敛

- [x] 生命周期、Recipe Lock 与重现约束合入 `pack.json`
- [x] Source Quality 合入 `SOURCE_MANIFEST.json`
- [x] 删除 `OBJECT_MAP` 与独立状态 Markdown 等重复投影
- [x] 来源工作流、生命周期和语义蒸馏编排分离
- [x] 可靠性、完整性、准确率进入确定性质量硬门
- [x] v0.3 Pack 可无损迁移到 v0.4，不改写 Skill 和评测内容

### Milestone 6：Stable Core 1.0

- [x] Pack 1.0 Schema 与 0.2/0.3/0.4 可恢复迁移
- [x] Source/Document/Chunk/FTS/ACL 原子提交与 active-version 后切换
- [x] Pack staging、跨进程锁、revision/CAS 和 intent-first 撤销
- [x] Source/Suite/Skill/Answer/Judge/Artifact Hash 发布绑定
- [x] Stable 发布要求 Provider 隔离或不同模型隔离
- [x] MIT、Security、Changelog、wheel/sdist 和隔离安装验证

---

## 设计决策记录

重要架构决策后续写入 `docs/adr/`：

```text
docs/adr/
├── 0001-universal-ir.md
├── 0002-profile-based-pipeline.md
├── 0003-canonical-evals.md
├── 0004-darwin-as-external-engine.md
└── 0005-private-person-consent.md
```

每个 ADR 记录：

- 背景
- 决策
- 替代方案
- 取舍
- 后果
- 未来复审条件

---

## 成功标准

one-skills 成功不是因为支持很多输入格式，而是因为：

1. 用户可以从复杂材料中得到真正可调用的能力
2. 每个能力都能追溯到来源
3. 每个 Skill 都知道何时使用和何时不用
4. 核心任务效果优于没有 Skill 的 baseline
5. 私人对象的授权和隐私边界可执行
6. 新证据进入后可以局部更新而非全量重做
7. Darwin 优化后只有可验证的改进被保留
8. 产物能在不同 Agent Runtime 中独立运行

---

## License 与参考实现边界

one-skills 参考了多个不同许可证的项目：

- `nuwa-skill`：MIT
- `darwin-skill`：MIT
- `neo-skills`：GNU AGPL v3
- `cangjie-skill`：GNU AGPL v3

在项目正式选择许可证前：

- 不直接复制参考仓库的大段实现文本
- 对方法论来源保留明确致谢和链接
- 引入代码、模板或衍生实现前单独做许可证审查
- 如果直接复用 AGPL 覆盖内容，必须评估相应开源义务

---

## FAQ

### one-skills 和知识库有什么区别？

知识库主要负责检索信息。one-skills 负责把信息转换为触发、判断和行动协议。两者可以组合，但不能互相替代。

### 能完整复制一个人吗？

不能。它只能复制有足够证据、可以表达并可以验证的部分。产物必须明确区分本人原话、观察事实和框架推断。

### 一个对象应该生成一个还是多个 Skill？

由能力边界决定。单一职责生成一个 Skill；存在多个独立触发场景时生成 Skill Pack，并建立路由关系。

### 为什么不直接把所有逻辑放进一个超级 SKILL.md？

巨型 Skill 会造成加载成本高、触发模糊、维护困难和测试不可归因。one-skills 统一的是协议和 IR，不是把所有能力塞进一个文件。

### 为什么直接使用 Darwin，而不是内建进化算法？

Darwin 已经提供独立评审、paired 比较、棘轮和人在回路。one-skills 应专注蒸馏质量，通过 Adapter 复用成熟优化器。

### 没有 sub-agent 能运行吗？

可以串行降级，但必须保留相同产物结构，并标记评测独立性降低。

---

## 致谢

one-skills 的设计建立在以下工作的启发之上：

- [nuwa-skill](https://github.com/alchaincyf/nuwa-skill)：人物思维与表达 DNA 蒸馏
- [cangjie-skill](https://github.com/kangarooking/cangjie-skill)：长内容方法论蒸馏
- [darwin-skill](https://github.com/alchaincyf/darwin-skill)：Agent Skill 的验证门控进化
- [Agent Skills](https://agentskills.io)：开放的 Skill 结构与生态

---

## 项目愿景

one-skills 希望形成一种新的知识交付单位：

不是一份读完即忘的文档，不是一段只在演示中有效的提示词，也不是一个无法验证的“数字分身”。

而是一套：

- 有来源的知识
- 有边界的判断
- 有步骤的执行
- 有反例的约束
- 有测试的能力
- 有版本的进化

最终，真正值得被保留下来的，不只是“一个人说过什么”或“一本书写了什么”，而是其中能够继续解决问题的能力。
