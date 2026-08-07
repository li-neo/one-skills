# 工程完成审计

审计时间：2026-08-07

本文件按项目公开承诺逐项列出权威证据。只有代码、可复跑测试、运行产物或外部 CI 可以证明完成；设计意图不算证据。

## 1. 参考架构吸收

| 要求 | 实现证据 | 验证证据 |
|---|---|---|
| neo-skills 十阶段状态机不可跳阶 | `pipeline.py` | `test_pipeline_blocks_at_independent_verification_and_cannot_skip` |
| neo-skills v0.2.8 路由与 Guided Controller | `routing.py`、`guided.py`、Session Schema | 拒答路由、检查点、授权、证据等级无损入 Pack 测试 |
| neo-skills v0.2.0 可复现 Pack | `RECIPE_LOCK.json`、`PROTECTED_CONSTRAINTS.json` | Recipe/Profile 一致性、Source/Eval hash 漂移门测试 |
| Evidence 强 Schema | `models.py`、`schemas/evidence.schema.json` | Evidence 校验贯穿 Pack 测试 |
| SSRF、读回、Darwin 降级 | `ingest.py`、`delivery.py` | 私网拒绝、安装/导出、`status: prepared` 测试 |
| cangjie 多视角提取 | `extraction.extract_candidates_with_model` | 并行 Profile views；非原文 quote 拒绝测试 |
| 三重验证与 RIA++ | `provider.verify_candidate`、Profile 编译契约 | 独立模型验证集成测试 |
| 原子 Skill、关系与压力测试 | `compiler.py`、canonical evals | 完整发布链测试 |
| 2026 Source-Set 质量门 | `source_quality.py`、Source Catalog Schema | 独立来源、角色覆盖、holdout 和质量哈希测试 |
| 2026 Skill Retrieval | `skill_retrieval.py` | 字段分离、背景 IDF、margin/abstain 与官方 frontmatter 测试 |
| 2026 Learning / Experience | `learning.py`、`experience.py` | 先修路径、掌握状态、复现门与 holdout 隔离测试 |
| v0.3 Object Overview / Portfolio | `overview.py`、`portfolio.py`、ProfileSpec | 来源定位、两次语义确认、长文本分批和候选降级测试 |
| v0.3 七类编译器 | `compilers/`、`capability_graph.py`、`artifacts.py` | 七 Profile 双层网络、图谱、Glossary、Digest 与学习投影测试 |
| v0.3 真实比较 | `comparison.py`、60 题 Mao suite | 完整 Answer/Judge 记录、匿名条件、综合分和不可补偿硬门 |
| v0.3 结构化进化 | `evolution.py` | 重复事件门、whole-folder patch、before/after、快照回滚测试 |

## 2. 蒸馏与 Profile

| 要求 | 实现证据 |
|---|---|
| 统一 Distillation IR | `schemas/distillation-ir.schema.json`、Pack `ir/distillation.json` |
| Person | 授权强制、advisor 边界、时序记忆 ADD/UPDATE/REVOKE |
| Content | RIA++ 执行契约、框架/原则/案例/反例/术语视角 |
| Methodology | 假设、诊断、机制、分支、完成与失效 |
| SOP | 角色、权限、逐步输入输出、异常、回滚、跨系统读回 |
| Tool | Schema、认证、最小权限、副作用、重试和读回 |
| Skill | 用途冻结、触发/工作流/边界诊断、回归保护 |
| Hybrid | 子对象路由、权限隔离、模块编排与整体闭环 |
| 插件 Profile | `one_skills.profiles` entry point；自定义 Profile 测试 |

七类固定路由基准：`benchmarks/profile-routing.json`，结果 `7/7`。

## 3. 知识、记忆与检索

| 要求 | 实现证据 |
|---|---|
| 不可变 Source/Document Version | `database.py`，同 URI 更新生成新 version |
| 内容寻址源文件 | `LocalBlobStore`；Manifest `raw_uri` 读回 |
| 全文、语义、关系混合检索 | SQLite FTS5、本地向量、RRF 和 lineage |
| Skill 字段召回 | name/description/trigger/boundary/procedure 独立 sparse+dense 分 |
| Source Quality | authority、directness、independence group、role、coverage 入库 |
| active version | 所有召回 SQL 在检索前过滤 |
| 多租户 ACL | tenant/principal/asset grants 在召回前过滤 |
| Person Memory | 三态更新、时序和向量字段 |
| 撤销与被遗忘 | Source revoke、Pack 失效、安装阻断、Deletion Log |
| 局部回归 | 血缘选择受影响 Skill tests，并保留全局安全/路由门 |
| PostgreSQL + pgvector | migration、HNSW、GIN、ACL 混合查询和负载工具 |
| 对象存储 | 本地内容寻址；可选 S3 Adapter |

当前实现外部证据：[GitHub Actions run 31000073539](https://github.com/li-neo/one-skills/actions/runs/31000073539)：

- PostgreSQL 16 + pgvector 容器健康；
- SQLite 全资产迁移成功；
- pgvector/tsvector ACL 混合检索成功；
- 8 workers × 20 次并发检索与审计写入成功；
- 连接关闭后重连健康检查成功。

## 4. 测试、发布与进化

| 要求 | 实现证据 |
|---|---|
| canonical eval 与 Darwin Adapter 分离 | `evals/canonical.json` + `test-prompts.json`，双哈希冻结并校验漂移 |
| 独立 Answer 结果 | `evaluation.aggregate_results`，缺失结果阻止发布 |
| 反触发/安全/相邻冲突 100% | `delivery._assert_tested` 硬门 |
| 实际效果不自评 | 静态 `actual_effect = 0`，只由外部结果折算 |
| 安装覆盖保护 | `.backup-<timestamp>` + SKILL.md 读回 |
| Runtime Adapters | Generic、Codex、Claude Code、Cursor ZIP 布局读回 |
| Darwin | 冻结保护项、paired 3/5 judges、prepared 降级 |
| Recipe Loop | Registry、固定 Benchmark、非补偿式晋升 |
| Knowledge Loop | 增量来源、版本切换、撤销、影响与回归 |
| Experience Loop | append-only 部署反馈、复现后候选、evaluation holdout 隔离 |
| Learning Loop | Pack 先修图、学习者掌握证据、间隔复习 |

## 5. 运行与规模化

| 要求 | 实现证据 |
|---|---|
| CLI | `one --help` 包含 source discover、semantic、compile、evaluate、compare、evolution 等 v0.3 入口 |
| HTTP API | Bearer 鉴权、限长 JSON、search、job submit/status |
| 持久 Worker | SQLite lease、超时重领、最大重试、错误隔离 |
| 批量并发 | 有界 ThreadPool，独立 Pack 和独立错误结果 |
| Audit | Job、ACL、撤销事件 append-only |
| CI | Python 3.10/3.11/3.12 + PostgreSQL/pgvector job |

## 6. 安全门

- 私网、环回、链路本地、保留地址和带凭据 URL 默认拒绝。
- URL 20 MiB、本地文件 100 MiB；DOCX/EPUB 解压后同样限额；PDF 有时间和输出限额。
- 非公开 Pack 不显式授权时禁止发送模型端点。
- Person Profile 必须声明 consent，`prohibited` 直接拒绝。
- API 非 loopback 绑定必须配置 Token；请求体最大 1 MiB。
- 模型提取 quote 必须逐字存在于指定 Chunk。
- 来源撤销后发布状态失效，不能继续安装。

## 7. 最终验证

```text
Local unit/integration tests: 37/37
Root Skill validation: 0 errors, 0 warnings
Profile benchmark: 7/7
Mao v0.3 Pack validation: 0 errors, 0 warnings
Mao blind comparison: 60/60, 99.7950 vs Cangjie 77.0797, lead 22.7153
Mao release: passed all hard gates, current phase evolve
Python CI 3.10 / 3.11 / 3.12: passed, run 31165723006
PostgreSQL + pgvector CI: passed, run 31165723006
Git diff check / compileall: passed
```

v0.3 实现 Commit `8d14ca5` 的权威外部证据：
[GitHub Actions run 31165723006](https://github.com/li-neo/one-skills/actions/runs/31165723006)。

已知运行依赖不是未实现功能：

- 三角色模型优先读取 Builder/Answer/Judge 独立配置；只有一套配置时标记
  `model-shared/session-separated`。没有任何端点时，外部 Runtime 可导入完整隔离
  Answer/Judge artifacts，但不得伪装成 provider-separated。
- Darwin 是外部进化引擎；未安装时只生成 `status: prepared` 的交接请求。
- S3 与 PostgreSQL 使用 `one-skills[production]` 可选依赖，本地模式不强制安装。
