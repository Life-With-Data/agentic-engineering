// Gates the generated documentation site. If a component is added/removed
// without running `bun run docs:build`, the reference pages (and landing-page
// stats) fall out of sync and this fails — naming the stale files.

import { describe, expect, test } from "bun:test"
import { readFileSync } from "fs"
import path from "path"
import { buildUpdates } from "../scripts/generate-docs"

const ROOT = path.resolve(import.meta.dir, "..")

describe("generated docs are in sync (run `bun run docs:build` if this fails)", () => {
  for (const { file, next } of buildUpdates()) {
    test(path.relative(ROOT, file), () => {
      expect(readFileSync(file, "utf8")).toBe(next)
    })
  }
})
