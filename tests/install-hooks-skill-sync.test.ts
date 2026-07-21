import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

// The wf-setup install-hooks reference bundles copies of the portable safety-hook scripts so
// they travel with skills-only installs (`npx skills add ...`), which never
// read plugin-level hooks. These tests pin the bundled copies byte-identical to
// the canonical scripts in plugins/agentic-engineering/scripts/ — fix a failure
// by editing the canonical script and running `bun run skills:sync`, never by
// editing the copy. (This portable-guard subset is pinned separately from the
// full bundle map in scripts/script-bundles.ts because it is its own contract:
// exactly these scripts must ship with skills-only installs.)

const PLUGIN_ROOT = join(import.meta.dir, "..", "plugins", "agentic-engineering");
const CANONICAL_DIR = join(PLUGIN_ROOT, "scripts");
const BUNDLED_DIR = join(
  PLUGIN_ROOT,
  "skills",
  "wf-setup",
  "scripts",
);

describe("wf-setup install-hooks reference bundled scripts", () => {
  const portable = [
    "block-db-push.py",
    "block-no-verify.py",
    "block-slack-webhook.py",
    "hook_payload.py",
    "prevent-main-commit.py",
  ];

  test("bundles the expected portable script set", () => {
    const bundled = readdirSync(BUNDLED_DIR).filter((file) => portable.includes(file));
    expect(bundled.sort()).toEqual(portable);
  });

  for (const file of portable) {
    test(`${file} is byte-identical to the canonical script`, () => {
      const canonical = readFileSync(join(CANONICAL_DIR, file), "utf8");
      const copy = readFileSync(join(BUNDLED_DIR, file), "utf8");
      expect(
        copy,
        `${file} copy out of sync with the canonical script — run \`bun run skills:sync\``,
      ).toBe(canonical);
    });
  }
});
