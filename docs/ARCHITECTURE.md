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
```

Recipe 晋升和 HTTP API 尚未提供 CLI，不应视为已实现接口。Application 层将逐步提供相同 Use Case，CLI 和未来 API 只是不同入口。

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

`li-neo/neo-skills` 是本项目的姊妹仓库，已实现一套可运行的最小蒸馏骨架（`src/neo_skills/` + `tests/` + `schemas/`）。本章把它经过验证的 **7 条硬约束**吸收进 one-skills 的架构规范，并明确边界与差异，用于指导后续代码实现，不重复造轮子也不忽视对方的教训。

### 19.1 Frontmatter 静态校验

**规则**：SKILL.md 的 YAML frontmatter 只允许两个键：`name` 和 `description`。任何附加键都必须报错。

- `name`：不超过 64 字符，正则 `[a-z0-9]+(?:-[a-z0-9]+)*`（lowercase hyphen-case）。
- `description`：不少于 40 字符，必须同时说明"做什么"和"何时触发"，静态校验须匹配 `use|when|for|使用|当|适用于|触发` 至少一处。
- SKILL.md 正文超过 500 行触发 `warning`，提示走渐进披露（把领域知识拆入 `references/`）。
- 正文中所有 `[label](path)` 相对引用必须解析到存在的本地文件。

**为什么**：这是跨 runtime（Claude Code / Codex / Cursor / OpenClaw）加载 Skill 的最低共识。任何 runtime 都不接受多余 frontmatter 键；没有 description 触发词的 Skill 会被静默忽略。

### 19.2 十阶段状态机不可跳阶

**规则**：Pipeline 十个阶段 `contract → ingest → map → extract → verify → compile → link → test → ship → evolve` 由 `PIPELINE_STATE.json` 持久化，`advance_phase(phase, status)` 只有在前置所有阶段状态为 `completed` 时才允许把当前阶段推进为 `completed`；否则拒绝并列出未完成前置。

**状态字段**：每个阶段记录 `status ∈ {pending, in_progress, completed, blocked}` 和 `updated_at`、`notes`。同时生成 `PIPELINE_STATE.md` 供人读，机器状态以 JSON 为准。

**为什么**：状态机是"断点续跑 + 追责 + 拒绝跳步"的唯一基础。文档里写"Phase 0-9"没有意义，只有落到不可跳过的执行契约才有意义。

### 19.3 证据账本的强 Schema

**规则**：`EVIDENCE_LEDGER.jsonl` 每行一条 JSON，字段必须齐备并通过 JSON Schema Draft 2020-12 校验：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | string | 非空、Pack 内唯一 |
| `claim` | string | 非空 |
| `evidence_type` | enum | `quote / verified_position / observed_behavior / third_party_view / model_inference / unknown` |
| `source` | string | 指向 `SOURCE_MANIFEST` 中的条目 |
| `locator` | string | 行号、章节路径、URL 片段等可回溯定位 |
| `confidence` | number | `[0, 1]` 闭区间 |
| `inference_level` | enum | `none / low / medium / high` |
| `permission` | enum | `public / authorized / private-local / unknown` |

**关键**：`evidence_type` 六类不可扩展，`inference_level` 分级强制透明化"这是原话还是模型推断"；违反的记录一律拒绝入账。

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

以下 5 点是 one-skills 相对 neo-skills 的核心增量，不能因为"向姊妹项目学习"而放弃：

1. **知识库层**：neo-skills 的 Pack 是孤岛，one-skills 在第 4-9 节定义了跨 Pack 的证据/能力索引和混合检索。
2. **Person Profile 记忆层**：neo-skills 每次人物蒸馏都从零开始；one-skills 第 6.1 节的 `person_facts` 支持 ADD/UPDATE/REVOKE 三态增量更新和语义召回。
3. **多租户 ACL**：neo-skills 无租户概念；one-skills 第 8.1 节要求 ACL 先于召回、进入数据库过滤条件。
4. **三类进化闭环**：neo-skills 只有 `evolve` 一个 Skill Loop；one-skills 第 2 节明确 Recipe Loop / Skill Loop / Knowledge Loop 三条独立闭环。
5. **候选抽取**：neo-skills 用正则关键词做 `bootstrap_candidates`，one-skills 应走"chunk + embedding + LLM 抽取 + 三重验证"完整链路，不退化为过程式脚本。

### 19.9 反向输出：one-skills 建议 neo-skills 补的 4 项

作为姊妹项目的双向反馈，one-skills 建议 neo-skills 未来演进补上：

1. `knowledge/` 命名空间和跨 Pack 索引（对应 one-skills 第 4-7 节）。
2. `person_facts` 增量记忆表和三态更新（对应 one-skills 第 6.1 节）。
3. Recipe Loop 与 Knowledge Loop 边界（对应 one-skills 第 2 节）。
4. `pack.py` 按 Control / Knowledge / Distillation / Evaluation 四平面拆分，避免过程式脚本 + 硬编码路径（对应 one-skills 第 3、12 节）。
