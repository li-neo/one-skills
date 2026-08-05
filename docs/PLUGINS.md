# Profile 与 Runtime 插件

one-skills 使用 Python entry points 扩展 Profile 和 Runtime，不要求修改核心仓库。

## Profile 插件

插件返回 `one_skills.profiles.Profile`：

```python
from one_skills.profiles import Profile

COMPLIANCE = Profile(
    name="compliance",
    map_dimensions=("controls", "evidence", "exceptions"),
    candidate_kinds=("rule", "control", "exception"),
    required_boundaries=("jurisdiction", "authorization"),
    compiler="control-pack",
)
```

插件项目的 `pyproject.toml`：

```toml
[project.entry-points."one_skills.profiles"]
compliance = "my_plugin:COMPLIANCE"
```

安装插件后即可执行：

```bash
one distill --source ./controls --type compliance
```

插件 Profile 会自动进入 workspace Recipe Registry。名称必须是 2–64 字符的 hyphen-case。

## Runtime 插件

插件返回 `one_skills.runtime.RuntimeAdapter`：

```python
from pathlib import PurePosixPath
from one_skills.runtime import RuntimeAdapter

RUNTIME = RuntimeAdapter(
    name="internal-agent",
    skills_prefix=PurePosixPath(".internal/skills"),
)
```

```toml
[project.entry-points."one_skills.runtimes"]
internal-agent = "my_plugin:RUNTIME"
```

使用：

```bash
one export ./packs/example --runtime internal-agent
```

所有 Runtime 导出都执行 ZIP 读回校验，并确认目标布局中存在 `SKILL.md`。
