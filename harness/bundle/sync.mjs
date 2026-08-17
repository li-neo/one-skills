/**
 * Refresh the bundle's embedded SKILL.md from the repository root, so a
 * standalone tarball/npm install carries the current skill body.
 *
 * Run from the repo root before packing:
 *   node harness/bundle/sync.mjs
 */

import { copyFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = fileURLToPath(new URL('../../SKILL.md', import.meta.url))
const target = fileURLToPath(new URL('./SKILL.md', import.meta.url))

copyFileSync(source, target)
console.log(`[one-skills] synced ${source} -> ${target}`)
