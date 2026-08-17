# Guided Distillation

Guided Distillation 用于用户只有模糊目标、口述经验或零散材料，尚不足以直接建立正式蒸馏契约的场景。它是十阶段 Pipeline 之前的材料发现控制器，不替代 `contract → ... → evolve`。

## 设计来源

该控制器吸收 `li-neo/neo-skills` v0.2.2 的三项设计：

1. 对话、材料和混合三种交互模式。
2. 每轮最多三个问题，避免一次性表单。
3. 范围、证据、地图、Claim、Capability、构建、评测和发布检查点。

one-skills 增加四项约束：

1. Person Session 在初始化时即强制 consent，不延迟到 Pack 创建。
2. 事件账本只追加，不通过重写模拟事件流。
3. `self_report` 等证据等级在创建 Pack 时直接写入 `EVIDENCE_LEDGER.jsonl` 和知识库 Claim。
4. 每条事件通过导出文档的独立 Section 关联到准确 Chunk，保留 Source → Chunk → Claim 血缘。

## 状态与真源

每个 Guided Workspace 包含：

```text
guided/example/
├── SESSION_STATE.json
├── SESSION_EVENTS.jsonl
├── SESSION_STATUS.md
├── INTAKE.md
└── sources/
    └── guided-session.md
```

- `SESSION_STATE.json`：当前阶段、检查点、证据计数和下一轮问题。
- `SESSION_EVENTS.jsonl`：append-only 事件真源。
- `SESSION_STATUS.md`：供人阅读的状态投影。
- `INTAKE.md`：人工确认的范围、权限和证据缺口。
- `guided-session.md`：可进入正式 Pack 的结构化对话来源。

## 会话状态机

```text
discover
  → scope
  → evidence_inventory
  → interview
  → map_confirm
  → capability_confirm
  → build
  → evaluate
  → ship
  → evolve
```

推进规则：

- `discover` 前必须设置首期目标能力。
- `scope` 等关键阶段必须先得到对应 checkpoint 的显式确认。
- `interview` 至少记录一条证据或明确的 evidence gap。
- 未来 checkpoint 不能提前确认。
- `rejected` checkpoint 不能推进。

语义内容只保留两次人工确认：

1. `map_confirm`：确认 Object Overview 的骨架、术语、张力和来源缺口；
2. `capability_confirm`：同时确认 Claim 等级、Capability Portfolio、降级与拒绝理由。

`scope`、`evidence_inventory` 仍是权限和材料完整性的确定性前置条件；
`build/evaluate` 由 Pack Gate 自动验证，避免对同一语义内容重复确认。发布仍需
`ship` 确认。

## 证据等级

| 等级 | 含义 | 默认置信度 | 推断等级 |
|---|---|---:|---|
| `self_report` | 用户对自身行为或观点的陈述 | 0.70 | low |
| `scenario_response` | 对假设场景的回答 | 0.65 | medium |
| `observed_behavior` | 有定位信息的真实行为观察 | 0.90 | none |
| `documented_result` | 有记录的结果 | 0.95 | none |
| `third_party_view` | 有定位信息的第三方观点 | 0.75 | low |
| `model_inference` | 模型推导 | 0.40 | high |
| `unknown` | 尚未分类 | 0.30 | high |

用户回答不能直接标成 `observed_behavior`、`documented_result` 或 `third_party_view`。强外部证据必须提供 locator 和明确 permission。`evidence_gap` 会保留在 Session 中，但不会伪装成 Pack Claim。

## 对象路由

Guided 层允许更贴近用户语言的对象，进入正式 Pipeline 时映射到七类 Profile：

| Guided Object | Profile |
|---|---|
| person | person |
| customer | hybrid |
| proposal | content |
| skill | skill |
| methodology | methodology |
| thought-system | hybrid |
| book / document | content |
| sop | sop |
| tool | tool |

## CLI

```bash
one guide init <workspace> --subject <name> --object <type> [scope options]
one guide set <workspace> [--target-capability ...] [--exclude ...]
one guide status <workspace>
one guide record <workspace> --kind <kind> --content <text> \
  --evidence-class <class> --permission <permission> --locator <locator>
one guide confirm <workspace> --checkpoint <name> --status confirmed
one guide advance <workspace>
one guide export <workspace>
one guide create-pack <workspace> --output <one-workspace> [--source <path>]
one validate <workspace>
one next <pack-path-returned-by-create-pack>
```

`create-pack` 至少要求 `scope` 与 `evidence_inventory` 已确认。创建后回答、纠正、假设、观察和结果事件会成为可检索 Claim，并保留原始事件 ID；材料清单和 evidence gap 只保留在会话审计中。

创建出的 Pack 不走更短的旁路，而是进入与 `one distill` 相同的正式十阶段 Pipeline。`create-pack` 输出包含统一的 `next` 对象；也可以随时运行 `one next <pack>`，依次完成 Object Overview 确认、模型验证、Portfolio 确认、编译、冻结评测、比较和受控发布。对于非公开 Pack，先检查 `next.endpoints`，确认授权覆盖实际模型端点后，再使用 `one next <pack> --allow-sensitive-data` 获取验证命令。
