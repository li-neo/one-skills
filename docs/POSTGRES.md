# PostgreSQL + pgvector 后端

本地 MVP 默认使用 SQLite FTS5 和本地特征向量。团队部署可迁移到 PostgreSQL 15+ 与 pgvector。

## 安装

```bash
python3 -m pip install -e '.[production]'
export ONE_SKILLS_POSTGRES_DSN='postgresql://user:password@host/database'
```

DSN 只通过环境变量传递，避免出现在 shell history 和进程参数中。

## 初始化与迁移

```bash
one postgres init
one postgres health
one postgres migrate --sqlite ./.one/knowledge.db
```

迁移按外键顺序复制全部核心表。不可变 Source/Event/Edge 使用幂等插入；Document active version、Document Version status、Run、Job 等可变状态使用主键 UPSERT，重复迁移会同步最新状态：

- Source、Document、Chunk、Claim、Capability 和血缘
- Person Profile 时序记忆
- Tenant、Principal 和资产 ACL
- Job Queue、Run 与 Audit Event

Chunk embedding 从 SQLite JSON 转换为 `vector(128)`；全文索引使用生成列 `tsvector` 和 GIN；向量索引使用 HNSW cosine。

## 生产负载验证

```bash
one postgres load-test \
  --query "删除流程如何验证闭环" \
  --iterations 1000 \
  --tenant team-a \
  --principal alice
```

报告给出结果数、P50、P95 和最大延迟。查询在全文和向量评分前执行 active-version 与 tenant/principal ACL 过滤。

## 当前边界

PostgreSQL Adapter 已实现初始化、全量迁移、健康检查、ACL-aware 混合检索和负载测试。当前核心写入流水线仍以 SQLite 作为本地事务真源，PostgreSQL 作为可扩展检索后端；切换为 PostgreSQL 单一写入真源前，需要在目标环境执行故障恢复、并发写入和容量测试。
