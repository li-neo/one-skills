/**
 * DeepSeek Harness plugin exposing the one-skills distillation methodology.
 *
 * Registers the repository's `SKILL.md` as a runtime skill on `ctx.skills`, so
 * a Harness agent can load the one-skills protocol (entry routing, the ten
 * distillation phases, evidence rules, and quality gates) as instructions.
 *
 * Load through a Web overlay, from the deepseek-harness checkout:
 *
 * ```sh
 * pnpm dsh web --patch ./harness/cordis.yml
 * ```
 *
 * Or hot-load on a running `dsh web` by inserting this plugin's entry into
 * the profile's live `cordis.patch.yml` (the HMR watcher will recompose).
 * @module one-skills/harness
 */

import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type { SkillRegistration } from '@deepseek-ai/dsh-skill'

/** Cordis plugin name. */
export const name = 'one-skills'

/** The `ctx.skills` registry service is required. */
export const inject = ['skills']

/** Skill name the one-skills methodology is registered under. */
const SKILL_NAME = 'one-skills' as const

/** Fallback routing description when the skill's own frontmatter lacks one. */
const FALLBACK_DESCRIPTION = 'Distill people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills.'

/** Absolute path of the repository `SKILL.md` beside the `harness/` plugin. */
const SKILL_PATH = fileURLToPath(new URL('../SKILL.md', import.meta.url))

/** Directory of the one-skills repository, the base for relative resource references. */
const RESOURCE_BASE = { kind: 'directory', path: fileURLToPath(new URL('../', import.meta.url)) } as const

/** Parsed result of a skill file's leading `---`-fenced frontmatter. */
interface ParsedSkill {
  /** Frontmatter key/value fields, quotes stripped. */
  readonly fields: Readonly<Record<string, string>>
  /** Skill body after the frontmatter block. */
  readonly body: string
}

/**
 * Parse the leading `---`-fenced frontmatter of a skill file.
 * @param source - the raw skill file contents.
 * @returns the parsed fields and the body after the frontmatter block.
 */
function parseFrontmatter(source: string): ParsedSkill {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(source)
  if (match === null) return { fields: {}, body: source }
  const frontmatter = match[1] ?? ''
  const fields: Record<string, string> = {}
  for (const line of frontmatter.split(/\r?\n/)) {
    const separator = line.indexOf(':')
    if (separator <= 0) continue
    fields[line.slice(0, separator).trim()] = line.slice(separator + 1).trim().replace(/^["']|["']$/g, '')
  }
  return { fields, body: source.slice(match[0].length) }
}

/** Register the one-skills methodology as a runtime skill on `ctx.skills`. */
export function apply(ctx: Context): void {
  console.log('[one-skills] apply() invoked — plugin loading')
  const source = readFileSync(SKILL_PATH, 'utf8')
  const { fields, body } = parseFrontmatter(source)
  const description = fields.description === undefined || fields.description === ''
    ? FALLBACK_DESCRIPTION
    : fields.description
  const registration: SkillRegistration = {
    name: SKILL_NAME,
    description,
    source: 'runtime',
    content: body,
    path: SKILL_PATH,
    resourceBase: RESOURCE_BASE,
  }
  ctx.skills.register(registration)
  console.log(`[one-skills] registered skill "${SKILL_NAME}" (${body.length} characters)`)
  // Sentinel file so any observer can confirm the plugin applied without
  // needing direct access to the server stdout.
  try {
    writeFileSync(new URL('./.loaded', import.meta.url), String(Date.now()))
  } catch {
    // Sentinel write is best-effort; don't block plugin load.
  }
  // Prove the registration is reachable through the registry: log the resolved
  // catalog once discovery settles.
  void ctx.skills.list().then((skills) => {
    const present = skills.some(skill => skill.name === SKILL_NAME)
    console.log(`[one-skills] catalog check: ${present ? 'skill present' : 'skill missing'} (${skills.length} skills listed)`)
  })
}
