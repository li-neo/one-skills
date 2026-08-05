# Profile 模板库

七类内置模板由 `one_skills.compiler.PROFILE_CONTRACTS` 维护，并与实际编译器共用同一份定义，避免文档模板与运行行为漂移。

导出可编辑 JSON：

```bash
one profiles --output ./profile-templates.json
```

每个模板包含：

- Profile 专项执行步骤
- 输出契约
- 不可违反的边界
- Profile 专项高风险测试及预期行为

内置 Profile：

- `person`
- `content`
- `methodology`
- `sop`
- `tool`
- `skill`
- `hybrid`

自定义 Profile 使用 [插件协议](../docs/PLUGINS.md)，不应直接修改内置模板。
