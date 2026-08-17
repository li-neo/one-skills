# DeepSeek Harness 插件制作与安装指南

本指南以 **one-skills → Harness 插件** 为完整实战案例，讲解如何把任意项目制作成 DeepSeek Harness（下文简称 dsh）插件、注册进正在运行的 Web UI，并附上最小骨架、**dsh 的加载与运行机制**、热加载、排错与卸载。按本指南操作，Agent 和人类开发者都能独立复现。

官方教程位于 <https://deepseek-harness.github.io/deepseek-harness/develop/basic/>；本文在官方最小骨架的基础上补充了**加载运行机制（第 4.4 节）、跨项目加载、技能注册实战、排错信号**，并把 one-skills 的完整实现作为可直接复用的样例。文中 `<one-skills-root>` 指你在本机克隆 one-skills 后的绝对路径（见第 2 节），没有写死任何机器地址。

---

## 1. 核心概念

| 概念 | 作用 |
|---|---|
| **插件** | 一个 ESM/TS 模块，必须导出 `name` 和 `apply(ctx)`，可选择性导出 `inject`、`Config`。框架加载时调用 `apply(ctx)`，通过 `ctx` 注册工具、技能、服务、事件监听等。 |
| **cordis.yml** | 插件组合的配置文件，顶层是 patch 条目数组（`- insert`/`- disable`/`- id` 等）。 |
| **Bundle（组合包）** | 附带一份 patch 的 npm 包，通过 `dsh.plugin.bundles` 声明，用 `dsh plugin add` 安装。 |
| **Profile** | `$DSH_HOME/profiles/<name>/` 下的一份可启动组合（例如 `web`、`headless`），它的 `cordis.patch.yml` 是**热加载的用户层**。 |
| **--patch overlay** | 启动时通过 `--patch <path>` 临时叠加的 patch，只在本次进程有效，重启后消失。 |
| **HMR 热加载** | 长驻界面（`dsh web`、`dsh headless` 等）监听 `$DSH_HOME/profiles/<name>/cordis.patch.yml` 和 `$DSH_HOME/cordis.patch.yml`，文件变更后自动 recomposition，**无需重启**。注意：`--patch` overlay **不**参与热加载。 |
| **ctx.skills** | 技能注册服务。运行时调用 `ctx.skills.register({ name, description, source: 'runtime', content, ... })` 即可把一段 Markdown 指令注册成模型可加载的 skill。 |
| **自动清理** | 通过 `ctx.effect(() => dispose)` 注册的资源、以及通过 `ctx.tools.register` / `ctx.skills.register` 等注册的条目，在插件卸载时自动清理，无需手动 removeListener。 |

关键约束（在官方文档与本项目源码中均已验证）：

- 插件路径在 patch 中**必须是绝对路径**；patch 文件只贡献配置，不会改变 loader 解析模块时使用的 profile 目录。
- 所有注册都是同步 effect：事件监听、工具、定时器都通过 `ctx.effect()` / 注册 API 声明，框架负责卸载时清理。
- 服务依赖通过 `inject: ['serviceName']` 声明；框架保证依赖就绪后才调用 `apply`。可选服务用 `ctx.get('name')`（返回 `undefined` 表示未挂载）。
- 技能名必须是 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）；`name`/`description` 必填且非空。
- ESM 全局：所有包都是 `"type": "module"`，源码使用 `.ts`，从源码启动走 `node --import tsx/esm`。
- 类型仅导入（`import type { ... }`）在运行时会被 tsx/esbuild 完全擦除，因此插件文件即使放在 dsh 仓库之外，只要不做运行时导入 dsh 包，就无需在插件所在项目里安装 `@deepseek-ai/*` 依赖。

---

## 2. 前置条件

- Node.js `^22.19 || >=24`，pnpm（推荐通过 corepack 或 Homebrew 安装）。
- 已按 README 完成 deepseek-harness 的"从源码运行"路径：
  ```sh
  git clone https://github.com/deepseek-ai/deepseek-harness.git
  cd deepseek-harness
  pnpm install
  pnpm run build
  pnpm dsh web            # 默认 http://127.0.0.1:3080
  ```
  从源码启动时命令是 `pnpm dsh ...`；通过 npm 全局安装后直接用 `dsh ...`。本指南统一用 `pnpm dsh`，npm 安装场景把它替换为 `dsh` 即可。
- 你想要集成进 Harness 的项目。one-skills 从 GitHub 克隆到任意目录（下文用 `<one-skills-root>` 表示该目录的绝对路径）：
  ```sh
  git clone https://github.com/li-neo/one-skills.git
  cd one-skills
  pwd        # 记下输出的绝对路径，作为 <one-skills-root>
  ```
  加载 one-skills 插件**不需要 Python 环境**（插件只把 `SKILL.md` 注册成技能指令，见第 4.4 节）。仅当你要让 Agent 真正执行蒸馏流程（`SKILL.md` 里的 `one ...` CLI 命令）时，才需要在本机安装 one-skills 的 Python CLI（`pip install -e .` 或 `python3 scripts/one.py`）并配置模型 API Key。

---

## 3. 最小骨架：5 行插件

这是官方教程里的 hello world，可用来快速验证环境。

```sh
mkdir -p scratch-plugin/src
```

`scratch-plugin/src/my-plugin.ts`：

```ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'hello-plugin'

export function apply(ctx: Context) {
  console.log('[hello-plugin] plugin loaded!')
}
```

`scratch-plugin/cordis.yml`（**把绝对路径换成你自己的仓库路径**）：

```yaml
- insert:
    - id: hello
      name: '/absolute/path/to/deepseek-harness/scratch-plugin/src/my-plugin.ts'
```

启动（叠加在 Web UI 上）：

```sh
pnpm dsh web --patch ./scratch-plugin/cordis.yml
```

终端会出现 `[hello-plugin] plugin loaded!`。这是一次性 overlay，进程结束就消失。

---

## 4. 实战：把 one-skills 注册为运行时 Skill

one-skills 本身是一个"技能蒸馏框架"，仓库根目录自带 `SKILL.md`（带 harness 兼容的 frontmatter：`name`/`description`）。我们把它的 SKILL.md 作为 Markdown 指令体注册成 `ctx.skills` 里的一个运行时技能——也就是 dsh Agent 能通过 `<available_skills>` 看到、并用 `skill({ name })` 工具加载的那条记录。

### 4.1 插件目录结构

在 one-skills 仓库内新建 `harness/` 目录：

```
one-skills/
├── SKILL.md                 # 既有的技能协议（带 frontmatter）
├── harness/
│   ├── plugin.ts            # 插件实现（本指南的核心）
│   ├── cordis.yml           # 可复用的 --patch 模板
│   └── README.md            # 本文件
```

### 4.2 plugin.ts（完整版，可直接复用）

下面是 one-skills 实际使用的插件，严格 TS 严格模式通过（`strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`）。关键设计点用注释说明：

```ts
/**
 * one-skills Harness plugin —— 把仓库根目录的 SKILL.md 注册为运行时 skill。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
// 只导入类型；运行时擦除，因此插件目录不需要安装 @deepseek-ai/dsh-skill。
// 这个 type-only import 同时会触发 dsh-skill 对 Context 的接口合并，
// 让 ctx.skills 在 TS 下有正确类型。
import type { SkillRegistration } from '@deepseek-ai/dsh-skill'

export const name = 'one-skills'

// 声明对 skills 服务的硬依赖；框架在依赖就绪前不会调用 apply。
export const inject = ['skills']

const SKILL_NAME = 'one-skills' as const
const FALLBACK_DESCRIPTION =
  'Distill people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills.'

// 通过 import.meta.url 定位 SKILL.md，让插件在任何 cwd 下都能正确解析。
const SKILL_PATH = fileURLToPath(new URL('../SKILL.md', import.meta.url))
const RESOURCE_BASE = {
  kind: 'directory',
  path: fileURLToPath(new URL('../', import.meta.url)),
} as const

interface ParsedSkill {
  readonly fields: Readonly<Record<string, string>>
  readonly body: string
}

/** 简单的 YAML frontmatter 解析器，剥离最外层的 --- 围栏，取出 description。 */
function parseFrontmatter(source: string): ParsedSkill {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(source)
  if (match === null) return { fields: {}, body: source }
  const frontmatter = match[1] ?? ''
  const fields: Record<string, string> = {}
  for (const line of frontmatter.split(/\r?\n/)) {
    const separator = line.indexOf(':')
    if (separator <= 0) continue
    fields[line.slice(0, separator).trim()] = line
      .slice(separator + 1)
      .trim()
      .replace(/^["']|["']$/g, '')
  }
  return { fields, body: source.slice(match[0].length) }
}

export function apply(ctx: Context): void {
  const source = readFileSync(SKILL_PATH, 'utf8')
  const { fields, body } = parseFrontmatter(source)
  const description =
    fields.description === undefined || fields.description === ''
      ? FALLBACK_DESCRIPTION
      : fields.description

  const registration: SkillRegistration = {
    name: SKILL_NAME,
    description,
    source: 'runtime', // 运行时注册；可选 'project-dsh' | 'project-agents' | 'custom' | ...
    content: body,
    path: SKILL_PATH,
    resourceBase: RESOURCE_BASE,
  }
  ctx.skills.register(registration)
}
```

要点回顾：

- `import type { Context } from '@deepseek-ai/cordis'` + `import type { SkillRegistration } from '@deepseek-ai/dsh-skill'` 都是 type-only，**插件目录无需安装 npm 依赖**，dsh 从源码启动时用 tsx 直接编译。
- `new URL('../SKILL.md', import.meta.url)` 是 ESM 下最可靠的相对资源定位方式；不要用 `process.cwd()` 拼接，因为用户可能从任意目录启动 dsh。
- `inject: ['skills']` 是硬依赖；若写成可选依赖（例如"有 skills 服务就注册，没有就跳过"），改用 `const skills = ctx.get('skills')` 判断即可。
- `source: 'runtime'` 标记这是运行时注册条目；也可填文档里列出的其他来源标签（`'project-dsh'`/`'bundled'`等），只影响显示元数据，不影响行为。
- `resourceBase` 让 SKILL.md 里的相对路径（图片、子模块引用等）在被 skill 工具加载时能正确解析。

### 4.3 cordis.yml（可复用模板）

`harness/cordis.yml`（模板，`<one-skills-root>` 是第 2 节里克隆 one-skills 后 `pwd` 得到的绝对路径）：

```yaml
# dsh Web overlay: 把 one-skills 插件插入 web profile。
# 用法（在 deepseek-harness 仓库根目录执行）：
#   pnpm dsh web --patch <one-skills-root>/harness/cordis.yml
# <one-skills-root> 是本机克隆 one-skills 后的绝对路径；插件路径必须写绝对路径。
- insert:
    - id: one-skills
      name: '<one-skills-root>/harness/plugin.ts'
```

`id` 在组合树中必须唯一；建议与插件的 `name` 一致。

### 4.4 dsh 是如何加载与运行 one-skills 的

dsh 是 **"一切皆插件"** 的架构，加载完全由 Cordis Loader 驱动。加载与运行链路如下：

```
dsh web 进程启动
  │
  ├─ 读取 web profile 组合 = Bundle 层 + 用户 patch 层 + 可选 --patch
  │     └─ 用户 patch 层 = $DSH_HOME/profiles/web/cordis.patch.yml   ← one-skills insert 在这里
  │
  ├─ Cordis Loader 解析 patch 里的这条 insert：
  │     - id: one-skills
  │       name: '<one-skills-root>/harness/plugin.ts'    ← 必须是绝对路径
  │
  ├─ 用 tsx（ESM hook）把 plugin.ts 实时转译成可执行模块
  │     （插件文件无需预先 build，dsh 启动/热加载时现编）
  │
  ├─ 读取模块导出的 name / inject / apply
  │     name   = 'one-skills'
  │     inject = ['skills']          ← 声明依赖技能注册服务
  │     apply(ctx)                    ← 框架等 skills 服务就绪后调用
  │
  ├─ apply() 在 dsh 进程内执行：
  │     1. readFileSync('<one-skills-root>/SKILL.md')   ← 读 one-skills 仓库的 SKILL.md
  │     2. 解析 frontmatter（name/description）
  │     3. ctx.skills.register({ name:'one-skills', description, source:'runtime',
  │                              content:<SKILL.md 正文>, resourceBase:<one-skills 目录> })
  │
  └─ 之后每个 Agent 会话：
       dsh-tool-skill 消费者读取技能注册表 → <available_skills> 出现 one-skills
       → Agent 调用 skill({name:'one-skills'}) → 把 SKILL.md 正文注入为指令
```

**运行位置与"要不要本地跑插件"**：

- **插件不是独立服务/进程，它直接跑在 `dsh web` 那个 Node 进程内部**（Cordis 的 in-process 插件模型）。你不需要单独启动"one-skills 插件服务"——只要 dsh web 在运行、插件文件在 patch 写死的绝对路径上，插件就被自动加载执行。
- **one-skills 目录无需 `npm install`**：插件只用 `import type`（运行时擦除）+ Node 内置模块，tsx 实时编译，不产生任何 npm 运行时依赖。
- **真正需要本机环境的只有蒸馏执行**：注册 skill（加载方法论）这一层完全不碰 Python。但如果 Agent 按 SKILL.md 实际执行蒸馏（`one route` / `one guide init` / `one source audit` / `one create-pack` 等），这些命令是 Agent 通过 dsh 的 shell 工具在**本机**跑的，那时才需要本机装好 one-skills 的 Python CLI（`pip install -e .`）并配置模型 API Key。

**HMR 热加载**：dsh 长驻进程用 HMR 服务监听 `cordis.patch.yml`——改文件加入 insert 就自动加载，删除就自动卸载，全程无需重启。这正是"为什么可以动态加载"的答案。

---

## 5. 三种加载方式

### 5.1 一次性 overlay：`--patch`（开发/临时验证）

```sh
pnpm dsh web --patch <one-skills-root>/harness/cordis.yml
```

- ✅ 零侵入，进程结束即清理。
- ❌ **不参与热加载**：改 `plugin.ts` 或 patch 文件都需要重启进程。
- ❌ 重启后消失，需要重复加 `--patch`。

### 5.2 写入 profile 的 `cordis.patch.yml`（**推荐：热加载**）

dsh 的每个长驻 profile 都会监听自己的 patch 文件，变更后自动 HMR 重组合：

- Web profile：`$DSH_HOME/profiles/web/cordis.patch.yml`
- Headless 等其他 profile：`$DSH_HOME/profiles/<name>/cordis.patch.yml`
- 机器级用户层（对所有 profile 生效）：`$DSH_HOME/cordis.patch.yml`

默认 `DSH_HOME=~/.dsh`，可用环境变量 `DSH_HOME=/some/path` 覆盖。

把 one-skills 的 insert 合并进该文件（**保留原文件顶部注释，把数组合并**）：

```yaml
# ...原有注释保留...
- insert:
    - id: one-skills
      name: '<one-skills-root>/harness/plugin.ts'
```

**保存后 1-3 秒内 dsh 自动重组合**，插件会被加载/卸载/替换，无需刷新页面之外的任何操作（Agent 新会话会立刻看到新 skill；当前会话下一轮 `<available_skills>` 会更新）。

验证小技巧：在 `apply(ctx)` 里加一行 `console.log('[one-skills] loaded')` 能在 dsh 启动终端看到；也可以写一个哨兵文件（例如 `writeFileSync(new URL('./.loaded', import.meta.url), String(Date.now()))`），通过文件存在性确认 apply 执行过。

### 5.3 打包为可安装 Bundle（发布给其他人用）

one-skills 已经按官方教程打包好，可以直接被 dsh 安装。bundle 位于 `one-skills/harness/bundle/`：

```
harness/bundle/
├── package.json       # 声明 dsh.bundle.patch
├── cordis.patch.yml   # bundle 层：按包名引用 dsh-plugin-one-skills
├── index.js           # 纯 ESM 插件（零运行时依赖，无需 build）
├── SKILL.md           # 内嵌技能体副本（打包前用 sync.mjs 刷新）
└── sync.mjs           # 从仓库根刷新 SKILL.md 副本
```

设计要点：

- **纯 JS、零运行时依赖**：`index.js` 只用了 `import type`（运行时擦除）和 Node 内置模块，因此**从 git / 本地 / tarball 安装都无需 build、无需 `allowBuilds` 授权**。
- **SKILL.md 解析顺序**：git 安装（整个仓库是包）时读仓库根 `../SKILL.md`（始终最新）；独立安装（tarball）时读 bundle 目录内 `./SKILL.md`。打包前运行 `node harness/bundle/sync.mjs` 刷新内嵌副本。
- **patch 按包名引用**（不是绝对路径），Loader 通过 profile 的 node_modules 解析到已安装的 bundle 代码。

#### 三种安装方式（任选其一）

**A. 本地路径安装**（开发/验证，最常用）：
```sh
cd deepseek-harness
pnpm dsh plugin --profile web add /absolute/path/to/one-skills/harness/bundle
```

**B. 直接从 GitHub 安装**（无需本地克隆，靠仓库根 `package.json`）：
```sh
pnpm dsh plugin --profile web add github:li-neo/one-skills
```
仓库根的 `package.json` 把整个 one-skills 仓库声明为 bundle（`main` → `harness/bundle/index.js`，`dsh.bundle.patch` → `./harness/bundle/cordis.patch.yml`）。因为是纯 JS 且无 `prepare` 脚本，git 安装无需构建授权。

**C. tarball 安装**（离线分发）：
```sh
cd one-skills && node harness/bundle/sync.mjs   # 刷新内嵌 SKILL.md
cd harness/bundle && pnpm pack                  # 生成 dsh-plugin-one-skills-1.0.0.tgz
# 在目标机器：
pnpm dsh plugin --profile web add ./dsh-plugin-one-skills-1.0.0.tgz
```

#### 验证安装

```sh
pnpm dsh --profile web --dump-config   # 应看到 "# == dsh-plugin-one-skills" 层和 one-skills 行
pnpm dsh web                            # 启动后终端出现 "[one-skills] bundle registered skill"
```

卸载：`pnpm dsh plugin --profile web remove dsh-plugin-one-skills`（同时移除依赖和对应层）。

> **注意与用户 patch 层的关系**：bundle 层在 profile 启动时组合，`cordis.patch.yml` 用户层在之后应用——后应用的行按 `id` 胜出。如果同时在用户 `cordis.patch.yml` 里手工 insert 了同名 `one-skills` 行，它会覆盖 bundle 行；从 bundle 安装后应删掉手工 insert，避免两套来源。

---

## 6. 插件还能做什么

one-skills 只使用了 `ctx.skills.register`。dsh 插件通过 `ctx` 可以：

| 能力 | API | 需要 inject |
|---|---|---|
| 注册运行时 skill | `ctx.skills.register({...})` | `['skills']` |
| 注册 skill provider（扫描目录、远程目录等） | `ctx.skills.registerProvider(ctrl => ({ name, list, get }))` | `['skills']` |
| 注册工具 | `ctx.tools.register(defineTool({...}))` | `['tools']` |
| 注册服务 | `ctx.service('name', class extends Service { ... })`（类形式插件） | — |
| 消费配置 | 导出 `Config` interface + Schemastery `Config` schema；框架校验后注入 `ctx.config` | — |
| 监听事件 | `ctx.on('event', handler)` / `ctx.effect(() => dispose)` | 视事件而定 |
| 定时器 | 通过 `ctx.timer` 或 `ctx.effect(() => { const t = setInterval(...); return () => clearInterval(t) })` | `['timer']`（定时器服务是 bundle 可选项） |

### 6.1 声明依赖（inject）

```ts
export const inject = ['skills', 'tools']

export function apply(ctx: Context) {
  // ctx.skills 与 ctx.tools 均已就绪且类型可访问
}
```

### 6.2 接受配置（Config）

```ts
import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'

export const name = 'my-plugin'

export interface Config {
  greeting: string
}
export const Config = Schema.object({
  greeting: Schema.string().default('hello'),
})

export function apply(ctx: Context) {
  console.log(ctx.config.greeting)
}
```

用户在 cordis.yml 中传入：

```yaml
- insert:
    - id: my-plugin
      name: '/abs/path/to/plugin.ts'
      config:
        greeting: 'hi'
```

### 6.3 三种插件形态

函数形式（最常用，本指南 one-skills 就是这种）：

```ts
export const name = 'my-plugin'
export const inject = ['skills']
export function apply(ctx: Context) { /* ... */ }
```

对象形式：

```ts
export default {
  name: 'my-plugin',
  inject: ['tools'],
  apply(ctx: Context) { /* ... */ },
}
```

类形式（用来向其他插件提供服务）：

```ts
import { Service, type Context } from '@deepseek-ai/cordis'

export default class MyService extends Service {
  static inject = ['tools']
  constructor(ctx: Context) { super(ctx, 'myService') }
}
```

> 不要混用默认导出和具名导出（`name`/`inject`/`apply`），否则 Loader 可能丢弃 inject（参见 `docs/postmortem/0001-acp-default-export-drops-inject.md`）。函数/对象形式统一用具名导出；类形式用默认导出。

---

## 7. 验证清单

插件加载后，可按下面顺序验证：

1. **进程日志**：启动终端或 HMR 触发时应看到插件的 `console.log` / `ctx.logger.info`。注意：`ctx.logger.info` 在 web profile 默认可能不输出到 stdout，**验证阶段用 `console.log` 更稳**。
2. **哨兵文件**：在 apply 里写一个时间戳文件，外部进程可以直接 stat。
3. **会话内技能目录**：新的 Agent 会话（刷新 GUI 即可）的 `<available_skills>` 系统提示里会出现你注册的技能名和描述。
4. **调用 skill**：在对话框输入技能名或说"使用 one-skills 帮我蒸馏一个 skill"，Agent 会调用 `skill({ name: 'one-skills' })` 工具加载完整 Markdown 指令体。
5. **API 侧**（调试用）：通过 WebSocket `/api/events.mux` 发 `skill.list` RPC 可拿到当前 session 的 skill 列表（这是 GUI 的 ui-skill 模块使用的通道）。

---

## 8. 排错

| 现象 | 可能原因 | 解决 |
|---|---|---|
| 终端只打印 URL 行，没有插件日志 | `ctx.logger.info` 没接 console exporter；或 patch 没被加载 | 用 `console.log` 验证；检查 cordis.patch.yml 是数组合法 YAML；用绝对路径；`- insert:` 缩进正确。 |
| `Error: EPERM: operation not permitted, open '~/.dsh/...'` | 从源码启动时沙箱/权限限制阻止写入 `~/.dsh` | 设置 `DSH_HOME` 到可写目录，或用有写权限的 shell 启动 dsh。 |
| `Cannot find module '@deepseek-ai/cordis'`（运行时） | 插件文件做了**运行时**（非 type-only）导入 | 把 `import { X }` 改为 `import type { X }`；若必须使用运行时值（例如 `defineTool`、`Service`），把插件放到 deepseek-harness 仓库内或通过 bundle 分发。 |
| `a skill named "X" is already registered` | 同一层已有同名 runtime skill，或重复 insert | 换个 id/name，或检查是否重复写入 patch。 |
| `invalid skill name` | 技能名不是 kebab-case（有大写、下划线、连续 `-` 等） | 改名成 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。 |
| 修改 plugin.ts 后没生效 | 用了 `--patch`（一次性 overlay，不 HMR）；或 patch 文件在 `--patch` 路径而非 profile 的 `cordis.patch.yml` | 改写到 `$DSH_HOME/profiles/web/cordis.patch.yml`；或重启带 `--patch` 的进程。 |
| GUI 里还是看不到 skill | `tool-skill` 在 host 层被 web-app bundle 禁掉了，skill 目录按 per-agent preset 注入；当前会话的 pre-step 还没注入新 catalog | 刷新页面开启新会话；per-agent preset 会在下次 step 重新拉取 catalog。 |

---

## 9. 卸载

- **一次性 overlay**：停止进程，去掉 `--patch` 参数即可。
- **Profile patch 层**：从 `$DSH_HOME/profiles/<name>/cordis.patch.yml`（以及 `$DSH_HOME/cordis.patch.yml`）里删掉对应的 `- insert:` 段并保存，HMR 会在 1-3 秒内卸载。
- **Bundle 安装**：`dsh plugin remove <pkg-name> --profile <name>`。
- **代码卸载验证**：删除 insert 段后，哨兵文件（如本指南中的 `harness/.loaded`）不会被删除（它只是 apply 时写入的），但新会话的 `<available_skills>` 中应不再出现该 skill。

---

## 10. 把本指南套用到你自己的项目

把任意项目改造成 Harness 插件，按这张清单走即可：

1. 确定"你要向 Agent 暴露什么"：
   - 一段稳定的 Markdown 指令（最常见，one-skills 这种）→ `ctx.skills.register`。
   - 一个可调用动作（CLI 包装、HTTP 调用、计算）→ `ctx.tools.register(defineTool(...))`。
   - 一组可被其他插件消费的服务 → 类形式插件 + `ctx.service()`。
2. 从 GitHub 克隆目标项目（`git clone <repo-url>`），记下绝对路径 `<project-root>`；在项目里建 `harness/plugin.ts`，用 `import.meta.url` 定位资源，只做 type-only 导入（避免引入 npm 运行时依赖）。
3. 在 `harness/cordis.yml` 写好 `<project-root>/harness/plugin.ts` 的 `- insert:` 模板。
4. 先用 `pnpm dsh web --patch <project-root>/harness/cordis.yml` 做一次性验证（机制见第 4.4 节）。
5. 稳定后，把 insert 合并进 `$DSH_HOME/profiles/web/cordis.patch.yml` 享受 HMR。
6. 要分发给别人时，按第 5.3 节打包为 bundle，用 `dsh plugin add` 安装。

## 参考

- one-skills 仓库：<https://github.com/li-neo/one-skills>
- 官方教程（本指南基础）：<https://deepseek-harness.github.io/deepseek-harness/develop/basic/>
  - 开发一个工具：`docs/user/develop/basic/tool.md`
  - 插件配置：`docs/user/develop/basic/config.md`
  - 打包与安装：`docs/user/develop/basic/publish.md`
- 框架概念：`docs/user/develop/framework/`（服务与依赖、事件、插件生命周期）
- Cordis 框架教程：`docs/cordis-tutorial/`（在临时目录动手构建，无需 API Key）
- 子系统参考：`docs/subsystems/skills.md`（技能注册表完整契约）
- 本仓库实现样例：`packages/skill/skill-badge/src/index.ts`（官方 bundle skill provider，最简洁的参考实现）
