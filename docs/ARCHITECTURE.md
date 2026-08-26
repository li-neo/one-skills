# one-skills 工程架构

> 本文描述 **1.0.0 纯文件（零数据库）核心**的实际架构。早期版本中的
> PostgreSQL / S3 / 多租户 ACL / Worker 队列 / HTTP API / 插件等企业级外壳
> 已在 v1.0 收敛中移除，本文不再描述。

## 1. 目标

one-skills 是一个"能力蒸馏"框架：把人物、内容、方法论、SOP、工具与既有 Skill
转换为可运行、可验证、可追溯的 Agent Skills。核心工程目标：

- **证据优先**：每个能力声明都指向可定位、可读回的来源。
- **可恢复**：十阶段状态机落盘在 `pack.json`，中断后可 `one status` 恢复。
- **可验证**：发布必须通过 no-skill / baseline / candidate 盲测与不可补偿硬门。
- **零外部依赖**：持久化全部为 Pack 内 JSON/JSONL 文件，无数据库、无服务器。

## 2. 顶层分层

```
CLI（one_skills.cli）                —— 唯一交互入口，按命令域组织
Control Plane（control / guidance）  —— 状态机门与"下一步动作"推荐
Distillation Pipeline（pipeline / source_workflow）
  ├─ ingest   ：来源展开、chunk 化、manifest 版本化
  ├─ map      ：Object Overview
  ├─ extract  ：候选 + 证据账本（EVIDENCE_LEDGER.jsonl）
  ├─ verify   ：V1 确定性门 + V2/V3 独立评审
  ├─ compile  ：Profile 编译器 → skills/<name>/SKILL.md + 能力网络
  ├─ link     ：CAPABILITY_GRAPH、LEARNING_PATH、INDEX
  ├─ test     ：结构测试 + 盲测对比
  ├─ ship     ：release / install / export
  └─ evolve   ：Darwin 交接 / patch 提案
Domain（profiles / compilers / validation / comparison / delivery …）
Infrastructure（utils / locking / provenance / schema_runtime / resources）
```

`platform.py` 曾在启动时声明"可选平台层"；该层已整体移除，CLI 不再包含任何
postgres / serve / job / batch / acl / monitor / benchmark / harness 命令。

## 3. 纯文件持久化

**不使用数据库**。工作区与 Pack 的全部状态都是可直接 git 管理的文件：

```
workspace/
├── .one/
│   ├── config.json          # 工作区配置（无 database 键）
│   ├── recipes.json         # Profile 活动 Recipe 注册表
│   ├── locks/               # 进程内/文件锁
│   └── revocations/         # 来源撤销意图
├── knowledge/
│   ├── sources/             # 内容寻址的原始来源（LocalBlobStore）
│   └── normalized/          # 归一化后的文档正文
└── packs/<slug>/
    ├── pack.json            # 元数据 + lifecycle（十阶段状态机）+ recipe_lock
    ├── SOURCE_MANIFEST.json # source → document → chunk 版本映射（血缘权威）
    ├── sources/chunks.json  # 全部 chunk（含 document_id/version/locator）
    ├── EVIDENCE_LEDGER.jsonl # 证据/声明账本（append-only）
    ├── OBJECT_OVERVIEW.json / VERIFIED_PORTFOLIO.json / CAPABILITY_GRAPH.json
    ├── candidates/ verified/ rejected/
    ├── skills/<name>/       # 唯一可发布单元（SKILL.md + capability.json + evals）
    ├── ir/distillation.json # 统一 IR
    └── reports/             # QUALITY.md / EVIDENCE_GRAPH.md / IMPACT.md
```

关键决策：**证据账本（EVIDENCE_LEDGER.jsonl）同时承担声明存储与血缘来源**，
取代了旧版 `claims` 表。`pack.json.lifecycle` 承担状态机，取代 `PIPELINE_STATE`
迁移路径仍保留，用于升级旧 Pack 文件夹。

## 4. 血缘与来源撤销（无数据库）

旧版用 SQLite `lineage_edges` 表回答"哪些 Skill 依赖这个来源"。现在由
`source_workflow.build_pack_edges(pack)` 从 Pack 平面文件重建：

- `SOURCE_MANIFEST.json` → `source → document → chunk`（produces）
- `EVIDENCE_LEDGER.jsonl` → `chunk/document → claim`（supports）
- `skills/*/capability.json` → `claim → capability → skill`（supports / produces）

`one lineage` 对全工作区 Pack 的边做 BFS；`one source-revoke` 据此计算受影响
Skill（manifest 中 source 置 `active=False`、账本中对应证据移入历史目录、下游
阶段置 blocked）。跨 Pack 的撤销扫描各 Pack 的平面文件，无需中央索引。

## 5. 检索（无数据库）

`retrieval.py` 保留 `tokenize` / `local_embedding` / `cosine_similarity` /
`reciprocal_rank_fusion` 四个原语（核心 ingest/extract 也使用它们）。
`HybridRetriever` 在构造时扫描 `workspace/packs/*/sources/chunks.json`，在内存
行上执行：

- `keyword_search`：token 子串命中计数
- `semantic_search`：本地特征哈希向量余弦，0.20 下限
- `graph_neighbors`：由 `EVIDENCE_LEDGER.jsonl` + `capability.json` 推导"共享
  能力"的无向邻域
- `search`：RRF 融合三条结果并按 `access_level` 过滤

无 ACL、无 FTS、无租户。`one skill-search` 直接对 Skill 目录做字段感知召回。

## 6. 对象 Profile

内置 Profile 收敛为六类：`content` / `methodology` / `sop` / `tool` / `skill` /
`hybrid`（外加 `auto` 检测）。`customer` / `proposal` / `thought-system` 等
输入仍会路由，但映射到共享 Profile（hybrid / content），不再有专属编译器。
`person` 专属 Profile（含 consent 门与记忆功能）已移除。每类 Profile 拥有：
`PROFILE_SPECS`（overview 章节 / extractor views / 评测类型）与 `compilers/<name>.py`
编译器。插件 entry-point 注册已移除，Profile 集合为静态内置。

## 7. 关键不变量

1. **十阶段不可跳阶**：`advance_phase` 按 `PHASE_INDEX` 校验，`pack.json.lifecycle`
   是唯一状态权威。
2. **证据必须可解析**：extract 后 `_index_evidence` 从 `chunks.json` 解析每个
   证据的 chunk，解析失败即 `PipelineError`，不留无主声明。
3. **发布门不可补偿**：质量、安全、正反例测试与盲测对比为硬门（见
   `comparison.py` / `delivery.py`）。
4. **只读恢复**：`one next` / `one status` 不改变状态；恢复只执行白名单动作。
5. **撤销留痕**：`source-revoke` 写入意图文件、DELETION_LOG 与账本历史。

## 8. 代码模块地图

- 编排：`pipeline.py`（提取/验证/编译/链接）、`source_workflow.py`（建包/
  ingest/血缘/撤销）、`lifecycle.py`（状态机与工作区）
- 控制面：`control.py`（统一 status 契约）、`guidance.py`（下一步推荐）、
  `guided.py`（引导会话）
- 领域：`ingest` / `extraction` / `overview` / `portfolio` / `compiler` +
  `compilers/` / `learning` / `capability_graph` / `artifacts`
- 质量：`validation` / `source_quality` / `distillation_quality` /
  `evaluation` / `comparison` / `provenance` / `reporting`
- 交付：`delivery`（release/install/export）、`runtime`（运行时适配）
- 进化：`evolution` / `experience`（Darwin 交接与反馈闭环）
- 基础设施：`utils` / `locking` / `storage`（LocalBlobStore）/
  `schema_runtime` / `resources` / `models` / `constants`

## 9. 测试策略

- 单元与集成测试全部基于 `unittest`（`python -m unittest discover -s tests`）。
- 测试直接调用库层（`create_pack`、`update_pack`、`HybridRetriever`、比较与
  发布门），并断言 Pack 平面文件产物。
- CI 运行多 Python 版本矩阵、`one --help`、`one validate .`、覆盖率门
  （`scripts/check_coverage.py`）与打包校验（`scripts/check_distribution.py`）。
