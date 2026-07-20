import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

// The wf-setup install-hooks reference bundles copies of the portable safety-hook scripts so
// they travel with skills-only installs (`npx skills add ...`), which never
// read plugin-level hooks. These tests pin the bundled copies byte-identical to
// the canonical scripts in plugins/agentic-engineering/scripts/ — fix a failure
// by re-copying the canonical script into the skill, never by editing the copy.

const PLUGIN_ROOT = join(import.meta.dir, "..", "plugins", "agentic-engineering");
const CANONICAL_DIR = join(PLUGIN_ROOT, "scripts");
const BUNDLED_DIR = join(
  PLUGIN_ROOT,
  "skills",
  "wf-setup",
  "scripts",
);

describe("wf-setup install-hooks reference bundled scripts", () => {
  const bundled = readdirSync(BUNDLED_DIR).filter((f) => f.endsWith(".py")).sort();

  test("bundles the expected portable script set", () => {
    expect(bundled).toEqual([
      "block-db-push.py",
      "block-no-verify.py",
      "block-slack-webhook.py",
      "hook_payload.py",
      "prevent-main-commit.py",
    ]);
  });

  for (const file of bundled) {
    test(`${file} is byte-identical to the canonical script`, () => {
      const canonical = readFileSync(join(CANONICAL_DIR, file), "utf8");
      const copy = readFileSync(join(BUNDLED_DIR, file), "utf8");
      expect(copy).toBe(canonical);
    });
  }
});
