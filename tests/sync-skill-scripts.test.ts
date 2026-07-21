import { describe, expect, test } from "bun:test";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "fs";
import os from "os";
import path from "path";
import {
  collectPairs,
  syncScripts,
} from "../scripts/sync-skill-scripts";
import { SCRIPT_BUNDLES } from "../scripts/script-bundles";

const ROOT = path.resolve(import.meta.dir, "..");

// Fixture: a miniature plugin tree with one canonical script, a deliberately
// desynced vendored copy, a missing vendored copy, and one entry whose
// canonical already lives inside the owning skill (must be skipped).
const FIXTURE_BUNDLES = {
  "wf-alpha": {
    "tool.py": "scripts/tool.py",
    "owned.sh": "skills/wf-alpha/scripts/owned.sh",
  },
  "wf-beta": {
    "tool.py": "scripts/tool.py",
  },
};

function makeFixture(): string {
  const plugin = mkdtempSync(path.join(os.tmpdir(), "skill-sync-"));
  mkdirSync(path.join(plugin, "scripts"), { recursive: true });
  mkdirSync(path.join(plugin, "skills", "wf-alpha", "scripts"), { recursive: true });
  writeFileSync(path.join(plugin, "scripts", "tool.py"), "print('canonical')\n");
  chmodSync(path.join(plugin, "scripts", "tool.py"), 0o755);
  writeFileSync(path.join(plugin, "skills", "wf-alpha", "scripts", "tool.py"), "print('stale')\n");
  writeFileSync(path.join(plugin, "skills", "wf-alpha", "scripts", "owned.sh"), "echo owned\n");
  // wf-beta's copy is intentionally absent: sync must create it.
  return plugin;
}

describe("sync-skill-scripts", () => {
  test("collectPairs skips entries that are their own canonical", () => {
    const pairs = collectPairs("/plugin", FIXTURE_BUNDLES);
    const labels = pairs.map((pair) => pair.label).sort();
    expect(labels).toEqual([
      path.join("skills", "wf-alpha", "scripts", "tool.py"),
      path.join("skills", "wf-beta", "scripts", "tool.py"),
    ]);
  });

  test("check mode reports desynced and missing copies without changing anything", () => {
    const plugin = makeFixture();
    try {
      const { updated, inSync } = syncScripts(plugin, FIXTURE_BUNDLES, true);
      expect(updated.sort()).toEqual([
        path.join("skills", "wf-alpha", "scripts", "tool.py"),
        path.join("skills", "wf-beta", "scripts", "tool.py"),
      ]);
      expect(inSync).toEqual([]);
      expect(readFileSync(path.join(plugin, "skills", "wf-alpha", "scripts", "tool.py"), "utf8"))
        .toBe("print('stale')\n");
    } finally {
      rmSync(plugin, { recursive: true, force: true });
    }
  });

  test("default mode repairs desynced copies, creates missing ones, and preserves modes", () => {
    const plugin = makeFixture();
    try {
      const first = syncScripts(plugin, FIXTURE_BUNDLES, false);
      expect(first.updated.length).toBe(2);

      const canonical = readFileSync(path.join(plugin, "scripts", "tool.py"), "utf8");
      for (const owner of ["wf-alpha", "wf-beta"]) {
        const vendored = path.join(plugin, "skills", owner, "scripts", "tool.py");
        expect(readFileSync(vendored, "utf8")).toBe(canonical);
        expect(statSync(vendored).mode & 0o777).toBe(0o755);
      }

      const second = syncScripts(plugin, FIXTURE_BUNDLES, true);
      expect(second.updated).toEqual([]);
      expect(second.inSync.length).toBe(2);
    } finally {
      rmSync(plugin, { recursive: true, force: true });
    }
  });

  test("the committed tree passes skills:check", () => {
    const { updated } = syncScripts(
      path.join(ROOT, "plugins", "agentic-engineering"),
      SCRIPT_BUNDLES,
      true,
    );
    expect(
      updated,
      "vendored skill scripts out of sync — run `bun run skills:sync`",
    ).toEqual([]);
  });

  test("the CLI --check entry point exits zero on the committed tree", () => {
    const result = Bun.spawnSync(
      ["bun", path.join(ROOT, "scripts", "sync-skill-scripts.ts"), "--check"],
      { cwd: ROOT },
    );
    expect(result.exitCode).toBe(0);
  });
});
