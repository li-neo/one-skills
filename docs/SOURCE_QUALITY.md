# 高质量来源发现与准入

## 原则

搜索结果不是证据，URL 数量不是独立来源数，单篇相关性也不是高质量来源集合。

one-skills 使用 `SOURCE_CATALOG.json` 在摄取前回答：

- 是否有一手材料；
- 是否有独立反证；
- 是否覆盖全部研究问题；
- 是否有验证锚点；
- 是否隔离了最终评测材料；
- 是否知道版本、时效、许可和访问边界。

## 创建模板

```bash
one source template --output SOURCE_CATALOG.json
```

候选来源字段：

| 字段 | 含义 |
|---|---|
| `ingest` | 实际摄取的本地捕获文件或 URL |
| `uri` | 原始来源身份 |
| `authority` | `primary/official/scholarly/reputable-secondary/community/unknown` |
| `directness` | `direct/derived/tertiary/unknown` |
| `independence_group` | 共同作者、机构、镜像或依赖链，相同则不算独立来源 |
| `role` | `evidence/context/counterevidence/verification_anchor/evaluation_only` |
| `coverage` | 精确对应 `research_questions` |
| `temporal_scope` | `historical/evergreen/current` |
| `usage_rights` | 允许全文、短引、仅链接等 |

## 审计

```bash
one source audit \
  --catalog SOURCE_CATALOG.json \
  --type person \
  --mode deep \
  --output SOURCE_QUALITY.json
```

`quick/standard/deep` 有不同默认门，Catalog 中的 `requirements` 可以提高但不应为了通过而降低高风险对象标准。

## 蒸馏

```bash
one distill \
  --workspace . \
  --source-catalog SOURCE_CATALOG.json \
  --type methodology \
  --mode deep \
  --name example \
  --access public
```

通过后：

- `evaluation_only` 不进入构建语料；
- 选中来源进入 `SOURCE_MANIFEST.json`；
- 来源质量进入 SQLite `source_assessments`；
- `SOURCE_QUALITY.json` 哈希进入 `PROTECTED_CONSTRAINTS.json`；
- 篡改质量报告会触发 `source.quality_drift`。

## 显式 Claim-Key

高质量捕获材料可以声明跨来源 Claim：

```text
Claim-Key: feedback-integrity
Claim-Statement: 可用的反馈方法必须包含独立坏消息通道。
Claim-Type: framework
Evidence: 该来源中可定位、可逐字核对的支撑句。
```

不同来源使用相同 `Claim-Key/Statement/Type` 后，系统合并证据并独立计算 `source_contexts` 和 `independence_groups`。内容冲突会报错，不由弱语义相似度强行合并。

## 网络发现建议

1. 先写研究问题和需要的来源角色。
2. 用官方站、作者仓库、论文数据库和档案馆发现候选。
3. 先登记 Catalog，再决定是否摄取。
4. 搜索摘要只用于发现，重要结论必须打开原文。
5. 页面失败、付费墙或版本不清时，记录缺口，不假装已读。
6. 对历史人物同时保留原著、版本研究、外部学术研究和严重失败证据。
