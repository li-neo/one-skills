# one-skills 工程架构

> 本文回答三个问题：蒸馏方案如何持续优化、蒸馏产物如何持续进化、技术文档如何保存并建立可追溯的知识库索引。

## 1. 架构目标

one-skills 需要同时管理三类长期资产：

1. **源知识**：文档、访谈、书籍、SOP、代码、记录和外部资料
2. **蒸馏逻辑**：Profile、提取器、验证规则、模板和评测标准
3. **蒸馏产物**：Claims、Capabilities、Skills、测试集和质量报告

这三类资产变化速度不同，不能混成一个目录或一套版本号。

系统必须满足：

- 原始来源不可变，可通过哈希定位
- 任何结论都能反查来源
- 任何 Skill 都能反查能力和证据
- 来源更新后只重建受影响的产物
- 蒸馏方案升级后能在固定基准集上比较
- Skill 优化后能回归验证并安全回滚
- 检索结果遵守文档访问权限
- 本地单机可以运行，后续可以平滑扩展

---

## 2. 三条持续优化闭环

持续优化必须拆成三条闭环。三者共享评测基础设施，但优化对象不同。

```text
┌───────────────────────────────────────────────────────────────┐
│ A. Recipe Loop：优化“怎么蒸馏”                                │
│ Profile / Extractor / Prompt / Rubric / Chunk Strategy        │
│ 固定 Benchmark → 候选方案 → 对比实验 → Promote / Reject        │
└──────────────────────────────┬────────────────────────────────┘
                               │ 生成
┌──────────────────────────────▼────────────────────────────────┐
│ B. Skill Loop：优化“蒸馏出来的 Skill”                          │
│ SKILL.md / resources / trigger / procedure / boundaries       │
│ Darwin → paired judges → regression → Keep / Revert           │
└──────────────────────────────┬────────────────────────────────┘
                               │ 依赖
┌──────────────────────────────▼────────────────────────────────┐
│ C. Knowledge Loop：优化“知识底座和索引”                         │
│ Source → Parse → Chunk → Enrich → Index → Retrieve → Feedback │
│ 新版本 / 新来源 / 失效检测 / 引用反馈 → 增量重建                 │
└───────────────────────────────────────────────────────────────┘
```

### 2.1 Recipe Loop：蒸馏方案进化

优化对象：

- Profile 定义
- 文档解析策略
- Chunk 规则
- Extractor 指令
- 候选验证规则
- Skill 模板
- Profile 专项 Rubric

每个 Recipe 使用独立版本：

```yaml
recipe:
  id: content-standard
  version: 1.3.0
  profile: content
  components:
    parser: markdown-structure@1.1.0
    chunker: semantic-section@1.2.0
    extractors:
      - framework@2.0.0
      - counterexample@1.1.0
    verifier: six-gates@1.0.0
    builder: skill-pack@1.4.0
```

#### 基准集

每个 Profile 维护固定的 Benchmark：

```text
benchmarks/
└── content/
    ├── cases/
    │   ├── book-small/
    │   ├── technical-rfc/
    │   └── course-transcript/
    ├── gold/
    │   ├── expected-capabilities.yaml
    │   ├── rejected-claims.yaml
    │   └── evals.yaml
    └── rubric.yaml
```

基准集至少覆盖：

- 正常输入
- 信息不足
- 来源冲突
- 高噪音长文
- 多个相近能力
- 不应生成 Skill 的材料

#### 方案晋升规则

Recipe 候选版本只有满足以下条件才晋升：

- 核心任务成功率提升
- Trigger 误触发不增加
- 证据覆盖率不下降
- 引用准确率不下降
- 安全与隐私测试 100% 通过
- 成本和延迟没有超过预算上限
- 人工抽检没有发现系统性失真

不要用单一总分决定晋升。安全、证据和反触发是硬门禁。

### 2.2 Skill Loop：Skill 产物进化

Skill Loop 直接复用 Darwin，优化对象限定为：

- `SKILL.md`
- Skill 自包含资源
- Trigger 和反 Trigger
- 执行步骤、分支和失败恢复
- 输出契约

不允许 Darwin 修改：

- 原始来源
- 已确认的事实
- 授权范围
- 核心用途
- 安全红线
- canonical evals 的预期结果

执行流程：

```text
1. 冻结 source_version、recipe_version、skill_version
2. 由 one-skills 生成 Darwin Adapter
3. Darwin 建立 baseline
4. 每轮只提出可归因修改
5. 独立 judges 做改前/改后 paired 比较
6. 多数判断 improved 或 tie 才暂时保留
7. 运行 one-skills 全量回归门禁
8. 通过后生成新 skill_version，否则 revert
```

Skill 版本必须记录其生成条件：

```yaml
skill:
  id: inversion-thinking
  version: 1.4.0
  generated_from:
    object_version: poor-charlies-almanack@2
    recipe_version: content-standard@1.3.0
    ir_version: sha256:...
  evolved_by:
    engine: darwin
    run_id: evo-20260805-001
```

### 2.3 Knowledge Loop：知识与索引进化

Knowledge Loop 负责：

- 新文档进入
- 文档版本变化
- URL 内容变化
- 来源撤销或失效
- 解析器升级
- Chunk 策略升级
- Embedding 模型升级
- 用户对检索质量的反馈

每次变化先做影响分析，不默认全库重建。

```text
source_version
    ↓
document_version
    ↓
chunk_version
    ↓
claim
    ↓
capability
    ↓
skill_version
    ↓
eval_case
```

如果一个 Source 被删除或撤销授权，沿这条依赖链找到并重建所有派生产物。

---

## 3. 四平面系统架构

```text
┌────────────────────────────────────────────────────────────┐
│ Control Plane                                              │
│ API / CLI / Workflow / Job Queue / Checkpoint / Policy     │
├────────────────────────────────────────────────────────────┤
│ Knowledge Plane                                            │
│ Source Store / Parser / Metadata / Search / Evidence Graph │
├────────────────────────────────────────────────────────────┤
│ Distillation Plane                                         │
│ Router / Profile / Extractor / Verifier / IR / Builder     │
├────────────────────────────────────────────────────────────┤
│ Evaluation Plane                                           │
│ Benchmark / Harness / Judges / Darwin / Metrics / Reports  │
└────────────────────────────────────────────────────────────┘
```

### 3.1 Control Plane

职责：

- 接收蒸馏、索引、评测和进化任务
- 维护状态机和断点
- 调度并行提取器
- 控制人工检查点
- 执行权限策略
- 记录每次运行的输入、配置和产物

任务状态：

```text
created → ingesting → mapped → extracting → verifying
        → building → validating → awaiting_approval
        → published

任意阶段 → failed / cancelled
published → superseded / revoked
```

### 3.2 Knowledge Plane

职责：

- 保存原始文件和规范化文档
- 维护文档版本与 Chunk
- 构建全文、向量和关系索引
- 提供带引用和权限过滤的检索
- 维护 Evidence Graph

### 3.3 Distillation Plane

职责：

- 根据对象选择 Profile
- 从检索结果和原文提取 Claims
- 验证并转换为 Capabilities
- 构建 Distillation IR
- 输出 Skill Pack

### 3.4 Evaluation Plane

职责：

- 运行 Recipe Benchmark
- 运行 Skill 行为测试
- 维护 baseline
- 独立评审
- 调用 Darwin
- 发布质量报告和进化记录

---

## 4. 存储架构

存储按“逻辑角色”而非“物理组件”划分。知识库与用户画像需要三种检索能力——**精确匹配、语义召回、关系遍历**，缺一不可，这是主流记忆系统的共识（见 4.3）。因此逻辑上是“完整三件套”，但物理上尽量合库，避免过早维护多套一致性。

### 4.1 存储职责

| 资产 | 本地 MVP | 规模化部署 | 为什么 |
|---|---|---|---|
| 源文件 | 本地文件系统 | S3 / R2 / MinIO | 适合不可变大对象 |
| Markdown、Schema、Recipe、Skill | Git | Git | 需要审查、diff、回滚 |
| 元数据和关系 | SQLite | PostgreSQL | 事务、过滤、影响分析 |
| 全文索引 | SQLite FTS5 | PostgreSQL `tsvector` | 不增加独立搜索集群 |
| 向量索引 | `sqlite-vec` | `pgvector`（与元数据同库） | 语义召回，与权限、元数据同库过滤 |
| 关系图 | 关系边表 | 边表 → 嵌入式图（Kuzu / FalkorDB-lite） | 实体、时序、多跳，先用边表顶着 |
| 用户画像记忆 | 见第 6 节 `person_*` 表 | 同左 + `pgvector` | 事实条目 + 语义召回 + 时序 |
| 运行日志 | JSONL + SQLite | PostgreSQL + 对象存储 | 可审计、可聚合 |
| 缓存 | 本地目录 | Redis，可选 | 只有并发量上来后才需要 |

### 4.2 三种检索角色，物理上尽量合并

三种角色都必须有，但“三件套”指的是逻辑能力，不是三套独立集群：

| 检索角色 | 负责 | 物理落地 |
|---|---|---|
| 精确 / 全文 | 术语、错误码、函数名、原句 | PostgreSQL `tsvector`（MVP：SQLite FTS5） |
| 语义 / 向量 | 同义表达、抽象概念、自然语言问题、记忆召回 | `pgvector`（与关系同库；MVP：`sqlite-vec`） |
| 关系 / 图 | Claim→Capability→Skill 血缘、人物-事件-偏好时序 | 关系边表；深度遍历需求出现后升级嵌入式图 |

关键取舍：**关系、全文、向量三种角色合并进同一个 PostgreSQL + pgvector 实例**，只有当出现深度多跳遍历时才引入嵌入式图引擎（Kuzu / FalkorDB-lite），而不是一上来就部署独立 Neo4j / Elasticsearch 集群。这样“三件套”是逻辑保证，物理上仍只维护 1–2 个进程。

### 4.3 GitHub 主流记忆 / 知识库系统的存储实践

调研五个高星项目，结论高度一致——都用“元数据/关系库 + 向量库 + 可选图库”的混合存储，没有一个用纯分层文件或纯向量：

| 项目 | Stars | 关系 / 元数据 | 向量 | 图 | 检索 |
|---|---|---|---|---|---|
| mem0 | 62k | SQLite | Qdrant | — | 语义 + BM25 + 实体，并行融合 |
| LightRAG | 38k | PostgreSQL | Milvus | Neo4j | 向量 + 图遍历 |
| Zep / graphiti | 29k | 图内置 | 嵌入 | Neo4j / FalkorDB / Kuzu | 语义 + BM25 + 图 |
| cognee | 29k | Postgres + pgvector | 多选 | Neo4j / Kuzu | 关系 + 向量 + 图 |
| letta / MemGPT | 24k | **PostgreSQL + pgvector（同一库）** | 同左 | — | 关系 + 向量 |

两条直接结论：

1. **纯分层 skill / 纯文件不足以做知识库和用户画像底座**——它无法支撑语义召回。分层文件的正确定位是“人工确认后的成品层”（对应第 5 节 `published/` 与 Git）。
2. **letta 用一个 PostgreSQL + pgvector 同时充当关系库和向量库**，直接印证本架构“合库优先”的选择；图能力在 graphiti / cognee 中也可用嵌入式引擎（Kuzu / FalkorDB-lite），无需独立集群。

---

## 5. 技术文档保存规范

### 5.1 文档分层

```text
knowledge/
├── sources/                 # 原始来源，不手工修改
│   └── <source-id>/
│       ├── manifest.yaml
│       └── blobs/
├── normalized/              # 解析后的规范化文档
│   └── <document-id>/
│       └── <version>.md
├── derived/                 # 自动提取的 Claim、Capability、摘要
│   └── <document-id>/
├── published/               # 人工确认后的知识文档
│   ├── concepts/
│   ├── methods/
│   ├── sops/
│   └── decisions/
├── indexes/                 # 本地索引文件，不进入人工编辑
└── registry/                # 文档注册表和 Schema
```

#### Source

保存输入原貌。相同内容通过 SHA-256 去重。Source 一旦登记，不原地覆盖。

#### Normalized

统一转换为 Markdown 或结构化 JSON，保留：

- 标题层级
- 表格
- 代码块
- 页码
- 时间戳
- 段落定位
- 原始来源映射

#### Derived

机器生成、可随时重建，包括：

- Chunk
- 摘要
- 实体
- Claims
- 关系
- Embeddings

#### Published

经过人工确认、可作为正式知识资产引用的文档。Published 内容必须进入 Git。

### 5.2 文档 Frontmatter

所有规范化和发布文档使用统一 Frontmatter：

```yaml
---
id: doc-01J5ABC...
title: "用户离职清理 SOP"
type: sop
status: published
version: 3
source_ids:
  - src-01J4...
owner: identity-team
created_at: "2026-08-01T10:00:00+08:00"
updated_at: "2026-08-05T15:30:00+08:00"
valid_from: "2026-08-05"
review_after: "2026-11-05"
access: internal
tags: [identity, offboarding, cleanup]
supersedes: doc-01J2...
---
```

### 5.3 稳定 ID

不要用文件路径作为主键。路径会变，ID 不应变化。

- Source ID：ULID
- Document ID：ULID
- Document Version：递增整数
- Chunk ID：`document_id + version + section_path + content_hash`
- Claim ID：ULID
- Capability ID：ULID
- Skill ID：稳定 slug + 内部 ULID
- Run ID：时间有序 ULID

### 5.4 不可变版本

更新文档时：

1. 新建 `document_version`
2. 保留旧版本
3. 标记 `supersedes`
4. 只重新解析发生变化的 Section
5. 原子切换 `active_version`

检索服务永远只读已发布的 `active_version`，不会看到索引构建到一半的状态。

---

## 6. 元数据模型

MVP 建议使用以下核心表：

```sql
CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  uri TEXT,
  content_hash TEXT NOT NULL UNIQUE,
  media_type TEXT NOT NULL,
  authority TEXT NOT NULL,
  access_level TEXT NOT NULL,
  license TEXT,
  captured_at TEXT NOT NULL
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  owner TEXT,
  access_level TEXT NOT NULL,
  active_version INTEGER
);

CREATE TABLE document_versions (
  document_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  source_hash TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  normalized_uri TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (document_id, version)
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  document_version INTEGER NOT NULL,
  section_path TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL,
  access_level TEXT NOT NULL
);

CREATE TABLE claims (
  id TEXT PRIMARY KEY,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  valid_from TEXT,
  valid_to TEXT
);

CREATE TABLE evidence_links (
  claim_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  quote_start INTEGER,
  quote_end INTEGER,
  PRIMARY KEY (claim_id, chunk_id, relation)
);

CREATE TABLE capabilities (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  profile TEXT NOT NULL,
  ir_uri TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE lineage_edges (
  from_type TEXT NOT NULL,
  from_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  to_type TEXT NOT NULL,
  to_id TEXT NOT NULL,
  PRIMARY KEY (from_type, from_id, relation, to_type, to_id)
);

CREATE TABLE skill_versions (
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  ir_hash TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (skill_id, version)
);

CREATE TABLE eval_runs (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  suite_version TEXT NOT NULL,
  result_uri TEXT NOT NULL,
  passed INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
```

### 6.1 用户画像记忆表（Person Profile）

用户画像不是一次性静态成品，而是随交互增量更新、可语义召回的**记忆层**，参照 mem0 / letta 的记忆模型。它复用统一证据模型：每条记忆是一个带来源、时效、置信度的 `person_facts` 条目，向量列供语义召回，图边表达人物-事件-偏好的时序关系。

```sql
-- 被蒸馏的“人”，一个 subject 对应一份持续演化的画像
CREATE TABLE person_subjects (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  relation TEXT,                      -- self / family / colleague / public 等
  access_level TEXT NOT NULL,         -- 画像高度敏感，ACL 先于召回
  active_version INTEGER,
  created_at TEXT NOT NULL
);

-- 记忆的原子单位：一条可召回、可更新、可撤销的事实
CREATE TABLE person_facts (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  dimension TEXT NOT NULL,            -- 心智模型 / 表达 DNA / 偏好 / 边界 / 事件
  statement TEXT NOT NULL,
  status TEXT NOT NULL,               -- active / superseded / revoked
  confidence REAL NOT NULL,
  valid_from TEXT,
  valid_to TEXT,                      -- 时序推理：事实何时生效、何时被取代
  supersedes TEXT,                    -- 指向被本条更新替代的旧事实
  embedding BLOB,                     -- 语义召回向量（pgvector / sqlite-vec）
  access_level TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 每条事实必须挂回证据 chunk，禁止无来源画像
CREATE TABLE person_evidence_links (
  fact_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  PRIMARY KEY (fact_id, chunk_id, relation)
);
```

记忆更新遵循 **ADD / UPDATE / REVOKE** 三态，而非直接覆盖：新事实写入并将旧事实标记为 `superseded`（记录 `supersedes` 指针），撤销走 `revoked`，从而保留完整时序，可回放“这个人的画像在某时点是什么样”。召回时按 `dimension` 过滤、向量语义排序、`access_level` 先行过滤，与第 8 节混合召回同一条链路。

生产环境再增加租户、ACL、Embedding、Job、Audit Event 等表。

---

## 7. 文档索引流水线

```text
Discover
  → Fingerprint
  → Store Raw
  → Parse
  → Normalize
  → Structural Chunk
  → Enrich
  → Index
  → Validate
  → Publish
```

### 7.1 Discover

支持：

- 文件或目录
- Git 仓库
- URL
- API
- 对话导出
- 工单与知识库导出

每个 Connector 只负责发现和下载，不负责业务提取。

### 7.2 Fingerprint

计算 SHA-256：

- 哈希已存在：复用 Source
- URI 相同、哈希变化：创建新 Source Version
- URI 变化、哈希相同：新增别名，不重复保存

### 7.3 Parse 与 Normalize

解析器输出统一 Document AST：

```yaml
document:
  title: "..."
  nodes:
    - type: heading
      level: 1
      text: "..."
      locator: {page: 1}
    - type: paragraph
      text: "..."
      locator: {page: 1, block: 3}
    - type: code
      language: python
      text: "..."
```

Markdown 是人类可读副本，AST 是结构化真值。不要只保留纯文本。

### 7.4 Chunk

优先结构切块，不使用固定字符数硬切：

1. 按标题、段落、表格和代码块划分语义单元
2. 小 Section 合并，大 Section 按段落边界拆分
3. 每个 Chunk 带上标题路径
4. 表格与解释段尽量放在同一 Chunk
5. 代码及其说明保持关联
6. 保留前后 Chunk 邻接关系

建议起始参数：

- 目标：400-800 tokens
- 最大：1200 tokens
- 重叠：只在跨段依赖时使用 10%-15%
- SOP：按步骤和异常分支切
- API 文档：按 endpoint / symbol 切
- 书籍：按小节和论证单元切

Chunk 参数必须进入版本号。调整 Chunk 策略相当于索引版本升级。

### 7.5 Enrich

为 Chunk 补充：

- 标题路径
- 文档类型
- 领域和标签
- 实体
- 时间有效性
- 来源可信度
- 权限
- 相邻 Chunk
- 原文定位

自动标签只用于召回增强，不能覆盖人工分类。

### 7.6 Index

建立三个索引：

1. **Lexical Index**：精确术语、错误码、API 名称
2. **Vector Index**：语义相近表达
3. **Relation Index**：来源、Claim、Capability 和 Skill 的依赖边

索引写入使用新 `index_version`，验证完成后原子切换别名：

```text
knowledge_active → knowledge_2026_08_05_002
```

切换失败时继续服务旧索引。

### 7.7 Validate

索引发布前检查：

- 文档数和 Chunk 数异常波动
- 空 Chunk
- 丢失标题路径
- 无法回到原文的 Locator
- 权限缺失
- Embedding 缺失
- 固定检索测试集 Recall@K
- 引用准确率

---

## 8. 检索架构

检索不是“向量 Top-K”。技术文档包含大量精确名称，必须使用混合检索。

```text
Query
  → Intent / Profile / ACL
  → Query Rewrite
  → Lexical Search ─┐
  → Vector Search  ─┼→ RRF Fusion
  → Metadata Filter ┘
  → Relation Expansion
  → Rerank
  → Context Assembly
  → Answer / Distillation
  → Citation Validation
```

### 8.1 权限先于召回

ACL 必须进入数据库过滤条件，不能先召回秘密文档再在应用层丢弃。

### 8.2 混合召回

- Lexical：标题、术语、错误码、函数名、原句
- Vector：同义表达、抽象概念、自然语言问题
- Metadata：类型、团队、时间、状态、可信度
- Relation：扩展到支持 Claim 的证据或由 Claim 派生的 Skill

初期使用 Reciprocal Rank Fusion，不急于训练复杂排序模型。

### 8.3 Context Assembly

上下文组装规则：

- 去重相同来源
- 保留文档层级
- 合并相邻 Chunk
- 优先一手来源
- 同时呈现关键冲突
- 控制单一文档占比
- 每段附 Source、Version 和 Locator

### 8.4 检索评测

维护固定查询集：

```yaml
- id: kb-001
  query: "用户离职时需要清理哪些系统？"
  expected_documents: [doc-offboarding-sop]
  expected_sections:
    - "账号禁用"
    - "权限回收"
    - "资源转移"
  forbidden_documents:
    - doc-onboarding-sop
```

核心指标：

- Recall@5
- MRR
- nDCG@10
- 引用准确率
- 无权限泄漏率
- 过期文档命中率
- 用户任务完成率

---

## 9. Evidence Graph 与影响分析

关系图是持续更新的关键，不只是可视化。

```text
Source
  └─ contains → Chunk
       └─ supports / contradicts → Claim
            └─ grounds → Capability
                 └─ implemented_by → SkillVersion
                      └─ covered_by → EvalCase
```

### 9.1 来源更新

新 Source Version 到达后：

1. 比较结构化 Section Hash
2. 找出新增、修改和删除 Chunk
3. 沿 `evidence_links` 找到受影响 Claims
4. 重新验证 Claims
5. 沿 `lineage_edges` 找到受影响 Capabilities 和 Skills
6. 只重建受影响产物
7. 运行受影响测试加核心全局回归

### 9.2 来源撤销

删除 Source 时不能只删除文件：

1. 将 Source 标记 `revoked`
2. 从活动索引中移除
3. 找到仅由该 Source 支持的 Claims
4. 将 Claims 降级或失效
5. 重建相关 Capabilities 和 Skills
6. 记录撤销审计

### 9.3 知识时效

Claim 支持：

- `valid_from`
- `valid_to`
- `review_after`
- `superseded_by`

技术文档到期后不立即删除，但检索排序降低，并触发 Owner Review。

---

## 10. 运行与事件模型

所有长任务写入 Job：

```yaml
job:
  id: job-01J...
  type: distill
  state: extracting
  target: object-01J...
  recipe_version: content-standard@1.3.0
  input_snapshot: sha256:...
  checkpoint:
    completed_extractors: [framework, vocabulary]
    pending_extractors: [counterexample]
```

核心事件：

```text
source.discovered
source.versioned
document.normalized
index.published
claim.changed
capability.invalidated
skill.built
eval.completed
skill.published
recipe.promoted
source.revoked
```

MVP 不需要 Kafka。先在数据库中实现 Transactional Outbox，由 Worker 轮询处理。只有吞吐量和团队边界明确后再引入消息系统。

---

## 11. 推荐技术栈

### 11.1 MVP

| 层 | 推荐 |
|---|---|
| 语言 | Python 3.12 |
| CLI | Typer |
| Schema | Pydantic |
| API | FastAPI，第二阶段再启用 |
| ORM / Migration | SQLAlchemy + Alembic |
| 元数据 | SQLite |
| 全文索引 | SQLite FTS5 |
| 向量索引 | sqlite-vec（与元数据同库） |
| 文件 | 本地文件系统 |
| 版本 | Git |
| 测试 | pytest |
| Workflow | 数据库状态机 + 本地 Worker |

选择 Python 的原因是文档解析、Embedding、评测和 Agent 工具生态更完整。向量能力从 MVP 起就通过 `sqlite-vec` 内嵌在同一个 SQLite 文件里——语义召回是知识库和用户画像的刚需，但它不构成“独立向量集群”，因此不违背合库原则。

### 11.2 规模化

| 层 | 推荐 |
|---|---|
| 元数据、全文、关系 | PostgreSQL |
| 向量 | pgvector |
| 源文件 | S3 / R2 / MinIO |
| 队列 | PostgreSQL Outbox；必要时再上 Redis / Kafka |
| Worker | 独立进程或容器 |
| 可观测性 | OpenTelemetry + Prometheus |
| 密钥 | 云 KMS 或 Vault |

不要在 MVP 同时引入 Kubernetes、Kafka、独立 Neo4j、Elasticsearch 和独立向量数据库集群。向量用内嵌方案（sqlite-vec / pgvector 同库），图先用关系边表——三种检索角色齐备，但物理上不拆成多套集群。

---

## 12. 代码模块

```text
one-skills/
├── src/one_skills/
│   ├── cli/
│   ├── api/
│   ├── domain/
│   │   ├── source.py
│   │   ├── document.py
│   │   ├── claim.py
│   │   ├── capability.py
│   │   ├── skill.py
│   │   └── evaluation.py
│   ├── application/
│   │   ├── ingest.py
│   │   ├── distill.py
│   │   ├── index.py
│   │   ├── retrieve.py
│   │   └── evolve.py
│   ├── profiles/
│   ├── parsers/
│   ├── extractors/
│   ├── builders/
│   ├── evaluators/
│   ├── repositories/
│   └── adapters/
│       ├── runtimes/
│       └── darwin/
├── schemas/
├── recipes/
├── benchmarks/
├── knowledge/
├── distillations/
├── tests/
└── docs/
```

依赖方向：

```text
CLI / API
   ↓
Application Use Cases
   ↓
Domain Model
   ↑
Repositories / Parsers / LLM / Darwin Adapters
```

Domain 不直接依赖数据库、向量库或具体模型。

---

## 13. 核心接口

```python
class Parser(Protocol):
    def parse(self, source: SourceVersion) -> DocumentAST: ...


class Chunker(Protocol):
    def chunk(self, document: DocumentAST) -> list[Chunk]: ...


class Extractor(Protocol):
    def extract(
        self,
        context: ExtractionContext,
        chunks: list[Chunk],
    ) -> list[Candidate]: ...


class Verifier(Protocol):
    def verify(
        self,
        candidate: Candidate,
        evidence: list[Chunk],
    ) -> VerificationResult: ...


class SkillBuilder(Protocol):
    def build(self, ir: DistillationIR) -> SkillPack: ...


class Evaluator(Protocol):
    def evaluate(
        self,
        target: SkillPack,
        suite: EvaluationSuite,
    ) -> EvaluationReport: ...
```

这些接口允许 Profile 组合不同组件，但 MVP 不需要为每个类建立复杂插件系统。先使用显式 Registry：

```python
PROFILE_REGISTRY = {
    "content": ContentProfile(...),
    "person": PersonProfile(...),
    "sop": SopProfile(...),
}
```

---

## 14. API 与 CLI 边界

当前已实现命令：

```bash
one init .
one distill --source ./docs --type sop --access authorized
one update ./packs/example --source ./docs/changed.md
one search "离职清理涉及哪些系统" --access authorized
one lineage --type source --id <source-id>
one source-revoke --id <source-id> --reason "来源方撤回授权"
one regression-plan ./packs/example --skill offboarding-cleanup
one verify-model ./packs/example
one test ./packs/example --results ./agent-results.json
one release ./packs/example
one install ./packs/example --target ~/.codex/skills
one export ./packs/example
one evolve ./packs/example --skill offboarding-cleanup
one recipe evaluate --baseline baseline.json --candidate candidate.json --budgets budgets.json
one serve --host 127.0.0.1 --port 8765
```

CLI 与 HTTP API 复用相同知识库、ACL 和持久 Job Queue。HTTP 写请求只创建任务，不绕过 Pipeline 状态机和发布门。

---

## 15. 可观测性

每次运行记录：

- Profile 和 Recipe 版本
- 输入 Snapshot Hash
- 使用模型和参数
- Token、成本和延迟
- 每阶段候选数和淘汰率
- 证据覆盖率
- 检索命中来源
- 测试通过率
- 人工修改
- 最终发布版本

重点告警：

- 来源解析失败率上升
- 无引用 Claims 增加
- Trigger 误触发率上升
- 向量索引和元数据数量不一致
- 过期文档命中率上升
- 无权限检索命中
- Recipe 新版在某类输入上系统性退化

---

## 16. 测试策略

### 16.1 单元测试

- Parser 保留结构和 Locator
- Chunk ID 稳定
- ACL 过滤
- 版本切换
- Lineage 影响遍历
- Darwin Adapter 格式转换

### 16.2 契约测试

- Profile 输入输出符合 Schema
- Repository 在 SQLite 和 PostgreSQL 行为一致
- Runtime Adapter 生成合法 Skill

### 16.3 集成测试

- 文件进入到索引发布
- 文档更新只重建受影响 Chunk
- Source 撤销后检索不可见
- Claim 失效触发 Skill 回归

### 16.4 端到端测试

- 文档 → Capability → Skill → Eval → Publish
- Recipe 新版 → Benchmark → Promote
- Skill → Darwin → Neo Regression → Keep / Revert

---

## 17. 分阶段实施

### Phase A：本地知识底座

目标：技术文档可保存、可版本化、可检索。

- 文件系统 Source Store
- SHA-256 去重
- Markdown / TXT Parser
- 结构化 Chunk
- SQLite 元数据
- SQLite FTS5
- sqlite-vec 向量索引（语义召回，与元数据同库）
- Source、Document、Chunk CLI
- 固定检索测试集

验收：

- 文档可增量更新
- 搜索结果能回到原文位置
- 精确与语义召回可混合排序
- 旧版本可查询
- 无权限文档不被召回

### Phase B：最小蒸馏闭环

目标：从技术文档生成一个可测试 Skill。

- Content 和 Skill Profile
- Claim、Capability 和 Distillation IR
- Skill Builder
- canonical evals
- 独立答题与评分
- Lineage

验收：

- Skill 的每个核心能力有证据
- Trigger、反 Trigger 和核心任务通过
- Source 更新能定位受影响 Skill

### Phase C：方案优化与 Darwin

目标：分别进化 Recipe 和 Skill。

- Recipe Registry
- Benchmark Runner
- Darwin Adapter
- paired 评审
- Promote / Revert
- 质量趋势报告

验收：

- Recipe 升级有可复现对照实验
- Skill 优化可回滚
- 测试不能被优化器静默修改

### Phase D：团队化与规模化

目标：多用户、内部知识和异步任务。

- PostgreSQL + pgvector
- 对象存储
- API 和 Worker
- ACL / Tenant
- Outbox
- 审计和可观测性

---

## 18. 最关键的架构决策

1. **Git 保存人工确认的知识与 Skill，数据库保存运行状态和索引。**
2. **原始来源不可变，更新通过版本追加，不原地覆盖。**
3. **Markdown 用于人读，Document AST 和 IR 用于机器运行。**
4. **全文、向量、关系检索共享同一权限模型。**
5. **Recipe、Knowledge、Skill 使用独立版本和独立进化闭环。**
6. **Darwin 只优化 Skill，不负责来源更新和 Recipe 晋升。**
7. **Lineage 是增量更新、撤销授权和可追溯性的基础。**
8. **知识库和用户画像必须同时具备精确、语义、关系三种检索能力，但优先合库实现，而非部署多套集群。**
9. **用户画像是记忆层而非静态成品：事实条目增量更新（ADD/UPDATE/REVOKE）+ 语义召回 + 时序保留。**
10. **先用合库的 SQLite/PostgreSQL（含 sqlite-vec/pgvector）解决问题，只有深度多跳遍历出现时才引入嵌入式图引擎。**

---

## 19. 从 neo-skills 借鉴的最小执行契约

`li-neo/neo-skills` 是本项目的姊妹仓库。本文最初吸收其最小蒸馏骨架的 7 条硬约束，2026-08-05 审计 v0.2.2（`104f966a`）的 IR / Lineage / Recipe、完整路径 Playbook 和 Guided Controller，并在 2026-08-06 继续审计 v0.2.8（`d88f6db`）的路由、控制面、来源同步、Runtime Adapter 与 Git 棘轮。已有能力不重复移植；新增设计按 one-skills 的知识库、权限与血缘协议重新实现。

### 19.1 Frontmatter 静态校验

**规则**：SKILL.md 的 YAML frontmatter 必须包含 `name` 和 `description`；按 Agent Skills 开放规范允许 `license`、`compatibility`、`metadata` 和实验性 `allowed-tools`，其他顶层键报错。

- `name`：不超过 64 字符，正则 `[a-z0-9]+(?:-[a-z0-9]+)*`（lowercase hyphen-case），并与父目录一致。
- `description`：1-1024 字符，应该同时说明"做什么"和"何时触发"；缺少触发信号产生 warning。
- `compatibility`：提供时为 1-500 字符。
- `metadata`：允许缩进的字符串键值映射，用于 one-skills 的 `activation`、`aliases` 等扩展。
- SKILL.md 正文超过 500 行触发 `warning`，提示走渐进披露（把领域知识拆入 `references/`）。
- 正文中所有 `[label](path)` 相对引用必须解析到存在的本地文件。

**为什么**：这是跨 runtime 加载 Skill 的开放规范。one-skills 早期“只允许两个键”的校验会错误拒绝合法的官方 Skill，已在 2026-08-06 修正。

### 19.2 十阶段状态机不可跳阶

**规则**：Pipeline 十个阶段 `contract → ingest → map → extract → verify → compile → link → test → ship → evolve` 由 `pack.json.lifecycle` 持久化，`advance_phase(phase, status)` 只有在前置所有阶段状态为 `completed` 时才允许把当前阶段推进为 `completed`；否则拒绝并列出未完成前置。

**状态字段**：每个阶段记录 `status ∈ {pending, in_progress, completed, blocked}` 和 `updated_at`、`notes`。v0.4 不再生成独立状态文件，避免同一生命周期出现多个事实源。

**为什么**：状态机是"断点续跑 + 追责 + 拒绝跳步"的唯一基础。文档里写"Phase 0-9"没有意义，只有落到不可跳过的执行契约才有意义。

### 19.3 证据账本的强 Schema

**规则**：`EVIDENCE_LEDGER.jsonl` 每行一条 JSON，字段必须齐备并通过 JSON Schema Draft 2020-12 校验：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | string | 非空、Pack 内唯一 |
| `claim` | string | 非空 |
| `evidence_type` | enum | `quote / self_report / scenario_response / verified_position / observed_behavior / documented_result / third_party_view / model_inference / unknown` |
| `source` | string | 指向 `SOURCE_MANIFEST` 中的条目 |
| `locator` | string | 行号、章节路径、URL 片段等可回溯定位 |
| `confidence` | number | `[0, 1]` 闭区间 |
| `inference_level` | enum | `none / low / medium / high` |
| `permission` | enum | `public / authorized / private-local / unknown` |

**关键**：`evidence_type` 使用 Schema 中的封闭枚举，`inference_level` 分级强制透明化"这是原话、自述、观察、结果还是模型推断"；违反的记录一律拒绝入账。

**为什么**：区分"原话/立场/观察/推断/未知"是所有蒸馏可信度的基石。one-skills 第 6 节的 `claims / evidence_links` 表原来只有 `confidence`，本条把 `evidence_type` 和 `inference_level` 提升为一等公民并纳入静态校验。

### 19.4 七类测试与独立评审隔离

**规则**：每个 Skill 必须携带 `test-prompts.json`（JSON 数组），至少覆盖以下三类且以下七种类型不可扩展：

- 强制覆盖：`should_trigger`、`should_not_trigger`、`edge_case`
- 可选但建议：`sibling_bait`（相邻 Skill 混淆测试）、`failure`、`safety`、`task_effect`

每条测试至少包含 `id / type / prompt / expected`；`id` 在文件内唯一。

**独立评审纪律**：
- 静态检查器**永远不填 `actual_effect` 分数**，只能填 0；只有独立 Agent 提交 `agent-results.json` 且 `passed` 字段齐备时才折算。
- 前向测试的提示语必须使用"`Use $<skill> at <path> to solve <real task>.`"格式，禁止告诉测试 Agent"这在测什么弱点"。
- 修改 Skill 后不得同步调整冻结测试来迁就答案；测试本身错误时必须记录理由并由用户确认。

**为什么**：创作者自评是所有 skill 质量崩坏的头号原因（对应 SkillLens/SkillOpt 论文中 LLM 自评仅 46.4% 准确率的结论）。

### 19.5 交付前"read-back verification"

**规则**：任何写入外部系统的操作必须遵循 `dry-run → 执行 → 读回校验 → 审计` 四步。具体到本项目：

- 安装 Skill：写入目标目录后必须读回 SKILL.md，任何一处缺失即视为失败。
- 导出 Pack：zip 打包后必须读回验证 zip 非空且包含预期文件。
- 覆盖已存在目标：必须先 `rename` 为 `.backup-<timestamp>` 再写新版本，无 `--force` 时直接拒绝。
- 与本文档第 4 节 `active_version` 原子切换配套：切换后必须回读校验查询命中的是新版本。

**为什么**：这是把"闭环交付"从口号变成机制的唯一办法，与你在项目记忆里"用户离职清理需涵盖所有关联系统"的原子闭环需求同源。

### 19.6 SSRF 与私网默认拒绝

**规则**：所有 URL 摄入路径默认拒绝解析到私有、环回、链路本地、保留、组播、未指定 IP 段的 hostname；重定向后的最终 URL 必须再校验一次；只有显式 `--allow-private-network` 时才放行。

- 校验点：`socket.getaddrinfo(hostname)` 返回的所有 IP 都必须是公网可路由地址。
- 尺寸限制：URL 内容最大 20 MiB、本地文件最大 100 MiB，超过直接拒绝，不试图截断。
- 编码降级顺序固定为 `utf-8-sig → utf-8 → gb18030 → big5 → latin-1`，失败时报错不猜。

**为什么**：SSRF 是 Agent 调用外部 URL 时最便宜、最关键的一道默认阈值；同时限制大小和编码链路避免"部分成功、部分猜测"的静默错误。

### 19.7 Darwin 降级契约

**规则**：`evolve` 阶段调用 Darwin 优化 Skill 时，如果本地没有可用的 `darwin-skill`：

- 只写 `evolution/DARWIN_REQUEST.md` 和 `evolution/darwin-request.json`，`status` 保持 `prepared`。
- 不修改任何 Skill 文件、不宣称"已进化"。
- 后续人工或系统在有 Darwin 时读取该请求文件继续，测试集必须保持冻结。

**Darwin 使用纪律**（有 Darwin 时）：
- 冻结测试集 + 冻结基线；每轮只改一个维度；同一裁判成对比较 before/after；3 个（必要时 5 个）裁判多数决；多数变差用 `git revert`；连续轻微改善或平局时停止。
- 结果按行追加 `evolution/results.tsv`：`timestamp / skill / round / dimension / commit / judges / better / tie / worse / decision / notes`。

**为什么**：Darwin 不可用时**沉默失败或虚假声称"已优化"是这类系统最常见的诚信崩坏点**。降级契约把"没做到"变成显式状态，而不是模糊承诺。

### 19.8 与 neo-skills 的差异（不倒退清单）

截至 neo-skills v0.2.8，双方都已有 IR、Lineage、canonical eval、Recipe Loop 与 Guided Controller。neo-skills 后续新增了拒答式对象路由、统一控制面、Guided 来源同步、Runtime Adapter 和用户确认的 Git 进化棘轮；完整差异见第 20 节。以下 5 点仍是 one-skills 的核心增量，不能因为"向姊妹项目学习"而放弃：

1. **知识库层**：neo-skills 的 Pack 是孤岛，one-skills 在第 4-9 节定义了跨 Pack 的证据/能力索引和混合检索。
2. **Person Profile 记忆层**：neo-skills 每次人物蒸馏都从零开始；one-skills 第 6.1 节的 `person_facts` 支持 ADD/UPDATE/REVOKE 三态增量更新和语义召回。
3. **多租户 ACL**：neo-skills 无租户概念；one-skills 第 8.1 节要求 ACL 先于召回、进入数据库过滤条件。
4. **生产运行面**：one-skills 已实现持久 Job Queue、Worker、鉴权 API、PostgreSQL/pgvector、对象存储和 Runtime Adapter；neo-skills 保持轻量本地 Pack。
5. **候选抽取**：neo-skills 用正则关键词做 `bootstrap_candidates`，one-skills 应走"chunk + embedding + LLM 抽取 + 三重验证"完整链路，不退化为过程式脚本。

### 19.9 反向输出：one-skills 建议 neo-skills 补的 5 项

作为姊妹项目的双向反馈，one-skills 建议 neo-skills 未来演进补上：

1. `knowledge/` 命名空间和跨 Pack 索引（对应 one-skills 第 4-7 节）。
2. `person_facts` 增量记忆表和三态更新（对应 one-skills 第 6.1 节）。
3. 多租户 ACL，并确保权限过滤发生在全文和向量召回之前。
4. Guided Session 创建 Pack 时把事件证据等级直接写入 Claim 和 Evidence Link，避免只导出 Markdown 后丢失等级。
5. `pack.py` 按 Control / Knowledge / Distillation / Evaluation 四平面拆分，避免过程式脚本 + 硬编码路径（对应 one-skills 第 3、12 节）。

### 19.10 Guided Distillation Controller

neo-skills v0.2.2 的最佳新增设计是把"用户没有完整材料"从失败状态改成一个显式、可恢复的材料发现流程。one-skills 采用以下机制：

- `discover → scope → evidence_inventory → interview → map_confirm → claim_review → capability_confirm → build → evaluate → ship → evolve` 会话状态机；
- 每轮最多三个问题；
- scope、证据、对象地图、Claim、Capability、构建、评测和发布的人类检查点；
- 自述、情景回答、观察行为、文档结果、第三方观点和模型推断的分级；
- customer、proposal、thought-system 等用户语言对象到七类正式 Profile 的路由。

one-skills 不直接复制参考实现的文件孤岛方式，而是增加四项平台约束：

1. Person Session 初始化即校验 consent 与 access；
2. `SESSION_EVENTS.jsonl` 只追加；
3. `create-pack` 将回答、纠正、假设、观察和结果按原证据等级写入 `EVIDENCE_LEDGER.jsonl` 和数据库 Claim，材料清单与缺口不伪装成 Claim；
4. 导出文档以事件 ID 分 Section，使每条 Claim 能建立 Source → Chunk → Claim 血缘。

完整操作协议见 [`GUIDED_DISTILLATION.md`](GUIDED_DISTILLATION.md)。

### 19.11 Recipe 与评测冻结

neo-skills v0.2.0 将 Recipe 和 canonical eval 从约定提升为 Pack 内的可验证资产。one-skills 采用并扩展该机制：

- 创建 Pack 时从 Registry 复制当前活动 Recipe 到 `pack.json.recipe_lock`；
- `pack.json.reproducibility` 冻结每个 Source Version、评测和 Skill 的内容哈希；
- Skill 编译时冻结 canonical suite 与 runtime `test-prompts.json` 的规范 JSON 哈希；
- Pack 校验、发布、安装、导出和 Darwin handoff 均拒绝 hash drift；
- canonical cases 必须与 runtime tests 一致，Adapter 漂移不能静默通过。

Recipe Registry 之后晋升新版本不会改变已有 Pack；需要使用新 Recipe 时必须创建新 Pack 或执行显式重蒸馏。

## 20. 2026 来源、召回、学习与经验闭环

完整论文和社区证据见 [`RESEARCH_2026_ARCHITECTURE_AUDIT.md`](RESEARCH_2026_ARCHITECTURE_AUDIT.md)。

### 20.1 Source-Set Quality Gate

过去的 Ingest 只验证文件安全、哈希和访问权限，没有证明“为什么选这些材料”。现在增加：

```text
Research Questions
  -> Candidate Source Catalog
  -> authority/directness/independence/role/coverage/rights
  -> document-set gate
  -> captured immutable sources
```

来源角色分为 `evidence / context / counterevidence / verification_anchor / evaluation_only`。最后一种不进入构建语料，用作 OpenSkill 式泄漏屏障。`independence_group` 显式记录共同作者、机构、镜像或依赖链，防止把同一内容的多个 URL 当作独立证据。

v0.4 将 Source Quality 合入 `SOURCE_MANIFEST.json.quality`，其哈希进入
`pack.json.reproducibility`；数据库中的 `source_assessments` 仍只是可重建索引。

### 20.2 Context Recurrence 与 Source Independence 分离

原 V1 只保存 `section_path`，会把同一文档两章当作独立来源。Candidate 现在分别保存：

- `source_contexts`：方法是否在多个语境复现；
- `source_ids`：涉及哪些来源；
- `independence_groups`：来源是否真正独立；
- `source_independent`：独立组是否至少为二。

Content/Methodology 可以从一本书中的多语境复现提取方法，但 Person/Hybrid 的人物稳定主张要求独立来源组。模型不能覆盖确定性的来源独立性门。

高质量人工捕获可使用 `Claim-Key/Claim-Statement/Claim-Type/Evidence` 显式声明跨来源 Claim Family。系统检查不同来源的声明一致性和独立组，不通过降低语义阈值猜测。

### 20.3 Field-Aware Skill Retrieval

Skill Bank 召回不再把整个 `SKILL.md` 压成一个向量，而是保留：

```text
name | description | triggers | anti_triggers | procedure | body
```

每字段独立计算 IDF lexical 与本地 dense 分，再按固定权重组合。结果必须同时通过绝对分和 top-two margin，否则返回 `confirm` 或 `abstain`。明确点名 Skill 时优先；反触发只按明确 lexical overlap 降权，避免完整边界因包含领域词而被过度惩罚。

这对应 Field-Aware Agent Skill Retrieval、SkillSight 与 SRA-Bench 对 skill shadowing、背景文本和 incorporation 的发现。

### 20.4 Learning Path 与 Learner State

`LEARNING_PATH.json` 是 Pack 正式产物：

- 编译前：从自然章节保留来源顺序；
- 编译后：从 Capability `depends_on` 生成先修图；
- 节点携带 objectives、mastery checks 和 source locators。

学习者状态单独写入 `learning/states/<learner>.json`，采用单写者更新；掌握证据与 Pack 知识源分离。当前使用透明阈值与间隔复习，不声称是经过真实学生数据训练的 Knowledge Tracing。

### 20.5 Experience Ledger

部署反馈写入 append-only `EXPERIENCE_EVENTS.jsonl`：

```text
task_signature + skill + outcome + correction + evidence_locator
```

`training` 与 `evaluation` 事件分离；同一失败至少两次、且 evidence locator 不同，才写入 `EXPERIENCE_CANDIDATES.json`。候选不会自动修改 Skill，仍须冻结 eval、before/after、独立评测和人工 keep/revert。

### 20.6 Source Update 失效语义

增量更新前先把旧 Evidence/Candidate/Decision 归档到 `audit/history/`。旧自动 quote 不再追加保留，非 quote 的会话与人工证据保留；随后从活动 Source Version 重新提取。

SQLite 中仅由非活动 Chunk 支持的 Claim 标为 `superseded`。这修复了“Pack 文件已更新但知识库仍返回旧 Claim”的双真源问题。

### 20.7 最新 neo-skills 差异

本轮已采纳 v0.2.8 的 Object Router 思想，`one route` 在低分或低 margin 时拒绝猜测。

以下保持 P1：

1. Guided 与 Pack 统一 `status/gate/allowed_actions`；
2. Guided → Pack 同步预览、撤回 tombstone 与 privacy purge；
3. 当前 Skill 内容哈希绑定 Answer Agent 测试；
4. Runtime-neutral 单请求 JSON Adapter；
5. 用户确认 Token 驱动的 Git candidate keep/revert 与中断恢复。

现有 API、Job Queue、ACL 与 Runtime Export 已覆盖部分 Harness 职责，但不应据此声称已实现上述精确控制契约。

## 21. v0.3 Semantic Compilation Plane

v0.3 保留十阶段控制平面，但把语义产物从通用模板中拆出：

```text
Source Candidates
  -> Source Catalog Gate
  -> Object Overview
  -> Profile-specific Extractor Views
  -> Candidate / Verified Portfolio
  -> Profile Compiler
  -> Public Router + Internal Modules
  -> Capability Graph
  -> INDEX / GLOSSARY / DIGEST / Learning Path
  -> Blind Baseline Evaluation
```

### 21.1 ProfileSpec

七类 Profile 分别声明 Object Overview sections、extractor views、compiler、
relation types、learning policy、evaluation types 和 module strategy。

统一 IR 只统一来源、证据、生命周期和评测，不再让人物、内容、方法、SOP、
工具、既有 Skill 和 Hybrid 共用一套最终 procedure。

### 21.2 双层能力网络

内容和方法论默认编译为：

```text
one public SKILL.md
  -> internal capability JSON
  -> references/modules/*.md
  -> module evals
```

只有总入口进入全局 Skill Retrieval；内部模块只在 Pack 已加载后进行二阶段路由。
这同时保留原子能力和可学习结构，并降低大型 Skill 库中的 shadowing。

### 21.3 语义确认

除范围、授权和来源质量等确定性门外，语义内容只有两个确认点：

1. Object Overview；
2. Verified Capability Portfolio。

确认绑定内容 Hash。Source 更新后对应产物必须标记 stale，不能复用旧确认。

### 21.4 真实效果

v0.3 测试记录保存完整 Answer Agent 输出、匿名 Judge 理由、角色模型、隔离等级、
Suite/Source Set/Skill/Answer Hash、token 和延迟。no-skill、开源 baseline 和
candidate 使用同题、同 Answer Agent、同预算。

综合分用于比较，不替代 safety、引用、反触发、sibling、Hash 和泄漏硬门。

### 21.5 结构化进化

重复失败或纠正才能生成：

```text
CREATE / UPDATE / MERGE / PRUNE / NOOP
```

Patch 以整个 Skill 目录为作用域，记录轨迹、before/after Hash、训练比较、快照和
用户 keep/revert。Canonical 与 holdout 不允许被 Patch 修改。

## 22. v0.4 Core Consolidation

v0.4 不增加 Profile、图谱或记忆概念，只收敛蒸馏核心。

### 22.1 一类数据一个权威所有者

| 数据 | 权威位置 |
|---|---|
| 对象、模式、生命周期、Recipe、重现约束 | `pack.json` |
| 来源版本与 Source Quality | `SOURCE_MANIFEST.json` |
| 对象整体理解 | `OBJECT_OVERVIEW.json` |
| Claim 证据 | `EVIDENCE_LEDGER.jsonl` |
| 能力选择与降级决策 | `VERIFIED_PORTFOLIO.json` |
| 评测输入与结果 | `evaluations/` |
| Job、Lease、ACL、Audit | 运行数据库 |

Capability Graph、Learning Path、Glossary、Digest、INDEX、Markdown 和 Skill 都是
可重建投影。投影可以读取权威资产，不能反向覆盖权威资产。

### 22.2 编排边界

```text
lifecycle.py          workspace + ten-phase state machine
source_workflow.py    create + ingest + update + revoke
pipeline.py           extract + verify + compile + link compatibility API
core_assets.py        authoritative asset compatibility boundary
```

`pipeline.py` 从 1299 行缩减到约 600 行。拆分依据是真实用例和状态所有权，不按
“未来可能有多个实现”预先创建大量 Repository Port。

### 22.3 核心质量门

`assess_distillation_quality()` 只读取已有权威资产，计算：

- 可靠性：来源 Hash、证据解析和 Recipe 身份一致；
- 完整性：Overview、研究问题覆盖和可执行字段完整；
- 准确率：Evidence ID 可解析、独立来源支持和 V1/V2/V3 结果。

三类指标分别报告，硬门不可互相补偿。v0.4 双层网络发布时必须全部通过，不生成
新的质量状态文件。

### 22.4 兼容与迁移

v0.2/v0.3 继续兼容读取。`one migrate <pack>` 将旧状态、Recipe、保护约束和
Source Quality 合入 v0.4 权威资产，并删除六个重复文件。迁移不修改 `skills/`、
评测答案或 Skill Hash。
