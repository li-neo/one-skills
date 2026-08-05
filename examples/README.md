# 可复现端到端示例

本示例使用公开的合成方法论材料，不含真实个人或客户数据。

## 1. 初始化并蒸馏

```bash
python3 scripts/one.py init /tmp/one-skills-demo
python3 scripts/one.py distill \
  --workspace /tmp/one-skills-demo \
  --source examples/sources/decision-bottleneck.md \
  --type methodology \
  --name decision-bottleneck \
  --access public
```

流水线会停在 `verify: blocked`。这是预期行为：V2 预测力不能由关键词规则自评。

## 2. 独立模型验证

```bash
export ONE_SKILLS_MODEL_BASE_URL="https://model.example/v1"
export ONE_SKILLS_MODEL_API_KEY="..."
export ONE_SKILLS_MODEL="model-name"

python3 scripts/one.py verify-model /tmp/one-skills-demo/packs/decision-bottleneck
```

也可以由人工独立验证后，对单个候选执行：

```bash
python3 scripts/one.py approve /tmp/one-skills-demo/packs/decision-bottleneck \
  --candidate <candidate-id> \
  --reason "能够回答材料未直接讨论的新资源分配问题"
```

## 3. 独立执行测试

把每个 Skill 的 `test-prompts.json` 交给未参与构建的 Answer Agent，记录：

```json
[
  {"id": "<test-id>", "passed": true, "actual": "实际行为摘要"}
]
```

构建器不得自己伪造这份文件。得到结果后执行：

```bash
PACK=/tmp/one-skills-demo/packs/decision-bottleneck
python3 scripts/one.py test "$PACK" --results /path/to/agent-results.json
python3 scripts/one.py release "$PACK"
python3 scripts/one.py install "$PACK" --target /tmp/one-skills-installed
python3 scripts/one.py export "$PACK" --output /tmp/one-skills-dist
python3 scripts/one.py evolve "$PACK"
```

`release` 只有在结果完整、总通过率达标，且安全、反触发、相邻冲突均 100% 通过时才会完成 `ship`。

## 4. 验证检索与增量更新

```bash
python3 scripts/one.py search "资源瓶颈怎么排序" \
  --workspace /tmp/one-skills-demo \
  --access public

python3 scripts/one.py update "$PACK" \
  --source examples/sources/decision-bottleneck.md
```

内容发生变化时会创建新的 `document_version`，原子切换 active version，并使下游阶段失效。影响范围记录在 `reports/IMPACT.md`。
