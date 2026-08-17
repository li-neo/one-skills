/**
 * dsh-plugin-one-skills — DeepSeek Harness bundle entry.
 *
 * Packaged build of `harness/plugin.ts`, written as plain ESM with zero
 * runtime dependencies so it installs from a local path, a tarball, or git
 * with no build step and no build authorization.
 *
 * Registers the one-skills distillation methodology (`SKILL.md`) as a runtime
 * skill on `ctx.skills`, so a Harness agent can load the protocol (entry
 * routing, the ten distillation phases, evidence rules, and quality gates) as
 * instructions.
 *
 * SKILL.md resolution order:
 * 1. `../SKILL.md` — the repository root, when installed as part of the
 *    one-skills repo (git install).
 * 2. `./SKILL.md` — the bundle directory, when installed standalone
 *    (tarball / npm); run `node harness/bundle/sync.mjs` before packing to
 *    refresh this copy.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/** Cordis plugin name. */
export const name = 'one-skills'

/** The `ctx.skills` registry service is required. */
export const inject = ['skills']

/** Skill name the one-skills methodology is registered under. */
const SKILL_NAME = 'one-skills'

/** Fallback routing description when the skill's own frontmatter lacks one. */
const FALLBACK_DESCRIPTION = 'Distill people, content, methodologies, SOPs, or existing skills into traceable, testable Agent Skills.'

/** Candidate SKILL.md locations, in resolution order. */
const SKILL_CANDIDATES = [
  new URL('../SKILL.md', import.meta.url),
  new URL('./SKILL.md', import.meta.url),
]

/**
 * Resolve the first existing SKILL.md and its resource base.
 * @returns the skill path and the directory that owns it.
 */
function resolveSkill() {
  for (const candidate of SKILL_CANDIDATES) {
    const path = fileURLToPath(candidate)
    try {
      readFileSync(path)
      const resourceBase = fileURLToPath(new URL('./', candidate))
      return { path, resourceBase }
    } catch {
      // Candidate missing in this layout; try the next one.
    }
  }
  const tried = SKILL_CANDIDATES.map((candidate) => fileURLToPath(candidate)).join(', ')
  throw new Error(`[one-skills] SKILL.md not found; tried: ${tried}`)
}

/**
 * Parse the leading `---`-fenced frontmatter of a skill file.
 * @param source - the raw skill file contents.
 * @returns the parsed fields and the body after the frontmatter block.
 */
function parseFrontmatter(source) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(source)
  if (match === null) return { fields: {}, body: source }
  const frontmatter = match[1] ?? ''
  const fields = {}
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

/** Register the one-skills methodology as a runtime skill on `ctx.skills`. */
export function apply(ctx) {
  const { path, resourceBase } = resolveSkill()
  const source = readFileSync(path, 'utf8')
  const { fields, body } = parseFrontmatter(source)
  const description = fields.description === undefined || fields.description === ''
    ? FALLBACK_DESCRIPTION
    : fields.description
  ctx.skills.register({
    name: SKILL_NAME,
    description,
    source: 'runtime',
    content: body,
    path,
    resourceBase: { kind: 'directory', path: resourceBase },
  })
  console.log(`[one-skills] bundle registered skill "${SKILL_NAME}" (${body.length} characters)`)
}
