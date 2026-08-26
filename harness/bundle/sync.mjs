/**
 * Refresh the bundle's embedded SKILL.md from the repository root, so a
 * standalone tarball/npm install carries the current skill body.
 *
 * Run from the repo root before packing:
 *   node harness/bundle/sync.mjs
 */

import { copyFileSync, cpSync, existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = fileURLToPath(new URL('../../SKILL.md', import.meta.url))
const target = fileURLToPath(new URL('./SKILL.md', import.meta.url))

copyFileSync(source, target)

// Ship the routing-index references so a standalone tarball/npm install can
// resolve SKILL.md's `references/*.md` links.
const referencesSource = fileURLToPath(new URL('../../references', import.meta.url))
const referencesTarget = fileURLToPath(new URL('./references', import.meta.url))
if (existsSync(referencesSource)) {
  mkdirSync(referencesTarget, { recursive: true })
  cpSync(referencesSource, referencesTarget, { recursive: true })
}

console.log(`[one-skills] synced ${source} -> ${target}`)
if (existsSync(referencesSource)) {
  console.log(`[one-skills] synced ${referencesSource} -> ${referencesTarget}`)
}
