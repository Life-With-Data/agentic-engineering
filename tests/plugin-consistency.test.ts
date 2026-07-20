// Guards against the "added a component but forgot to update X" class of drift.
// Every declared count / list / version that describes the agentic-engineering
// (core) plugin is checked against the filesystem truth, and every other plugin
// under plugins/ gets basic checks (skill count in descriptions, version parity
// with marketplace.json, skill frontmatter). Runs in CI via `bun test`.
//
// If this fails: the message names the exact file + component that is out of
// sync. Fix the source of truth (add the missing row, bump the count, etc.) —
// do not relax the assertion.

import { describe, expect, test } from "bun:test";
import { existsSync, readdirSync, readFileSync } from "fs";
import path from "path";
import { parseFrontmatter } from "../src/utils/frontmatter";

const ROOT = path.resolve(import.meta.dir, "..");
const PLUGINS_DIR = path.join(ROOT, "plugins");
const CORE_PLUGIN_NAME = "agentic-engineering";
const PLUGIN = path.join(PLUGINS_DIR, CORE_PLUGIN_NAME);

function mdFilesRecursive(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...mdFilesRecursive(p));
    else if (entry.name.endsWith(".md")) out.push(p);
  }
  return out;
}

function skillDirsIn(pluginDir: string): string[] {
  const dir = path.join(pluginDir, "skills");
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter(
      (e) => e.isDirectory() && existsSync(path.join(dir, e.name, "SKILL.md")),
    )
    .map((e) => e.name);
}

// ---- filesystem truth -------------------------------------------------------

const agentFiles = mdFilesRecursive(path.join(PLUGIN, "agents"));
const skillDirs = skillDirsIn(PLUGIN);

const nonCorePlugins = readdirSync(PLUGINS_DIR, { withFileTypes: true })
  .filter(
    (e) =>
      e.isDirectory() &&
      e.name !== CORE_PLUGIN_NAME &&
      existsSync(path.join(PLUGINS_DIR, e.name, ".claude-plugin/plugin.json")),
  )
  .map((e) => e.name)
  .sort();

const counts = {
  agents: agentFiles.length,
  skills: skillDirs.length,
};

const pluginJson = JSON.parse(
  readFileSync(path.join(PLUGIN, ".claude-plugin/plugin.json"), "utf8"),
);
const marketplace = JSON.parse(
  readFileSync(path.join(ROOT, ".claude-plugin/marketplace.json"), "utf8"),
);
const mcpCount = Object.keys(pluginJson.mcpServers ?? {}).length;

const pluginReadme = readFileSync(path.join(PLUGIN, "README.md"), "utf8");
const rootReadme = readFileSync(path.join(ROOT, "README.md"), "utf8");
const indexHtml = readFileSync(path.join(ROOT, "docs/index.html"), "utf8");

// ---- declared counts match the filesystem ----------------------------------

describe("declared counts match filesystem", () => {
  test("plugin.json description", () => {
    expect(pluginJson.description).toContain(`${counts.agents} agents`);
    expect(pluginJson.description).toContain(`${counts.skills} workflow skills`);
  });

  test("marketplace.json description", () => {
    const desc = marketplace.plugins[0].description;
    expect(desc).toContain(`${counts.agents} specialized agents`);
    expect(desc).toContain(`${counts.skills} workflow skills`);
  });

  test("plugin README components table", () => {
    expect(pluginReadme).toContain(`| Agents | ${counts.agents} |`);
    expect(pluginReadme).toContain(`| Skills | ${counts.skills} |`);
    expect(pluginReadme).toContain(`| MCP Servers | ${mcpCount} |`);
  });

  test("root README components table", () => {
    expect(rootReadme).toContain(`| Specialized agents | ${counts.agents} |`);
    expect(rootReadme).toContain(`| Workflow skills | ${counts.skills} |`);
    expect(rootReadme).toContain(`| MCP servers | ${mcpCount} |`);
  });

  test("docs/index.html landing-page stats (agents, skills, mcp)", () => {
    // Every stat on the landing page is marked data-stat="<key>" and filled by
    // scripts/generate-docs.ts. Assert EVERY occurrence (cards + hero + CTA
    // prose) matches the filesystem, so a stale hardcoded number can't slip in.
    // Skills (like all landing stats) are marketplace-wide: core plugin + every other plugin under plugins/.
    const totalSkills =
      counts.skills +
      nonCorePlugins.reduce(
        (n, p) => n + skillDirsIn(path.join(PLUGINS_DIR, p)).length,
        0,
      );
    const statOccurrences = (key: string) =>
      [
        ...indexHtml.matchAll(
          new RegExp(`data-stat="${key}"[^>]*>([^<]+)<`, "g"),
        ),
      ].map((m) => m[1]);
    const expectAll = (key: string, expected: string | number) => {
      const found = statOccurrences(key);
      expect(found.length).toBeGreaterThan(0); // the marker must exist
      for (const v of found) expect(v).toBe(String(expected));
    };
    expectAll("agents", counts.agents);
    expectAll("skills", totalSkills);
    expectAll("mcp", mcpCount);
    expectAll("version", pluginJson.version);
  });
});

// ---- version parity ---------------------------------------------------------

describe("version parity", () => {
  test("plugin.json and marketplace.json agree", () => {
    expect(pluginJson.version).toBe(marketplace.plugins[0].version);
  });
});

// ---- release-please can bump the docs version -------------------------------
//
// docs/index.html embeds the plugin version (data-stat="version"), filled by
// `bun run docs:build` from plugin.json. On a release PR, release-please bumps
// plugin.json but NOT generated files — so unless index.html is registered in
// release-please's extra-files (as a `generic` updater keyed on an
// `x-release-please-version` comment), its version lags and the "landing-page
// stats" + "docs in sync" tests fail *only in the release PR*, where the drift
// exists transiently. The generic updater no-ops silently if the annotation is
// missing or drifts off the version line, so this asserts the whole mechanism
// stays wired up — catching a regression on the offending PR, not at release.

describe("release-please bumps the docs version", () => {
  const rpConfig = JSON.parse(
    readFileSync(path.join(ROOT, ".github/release-please-config.json"), "utf8"),
  );
  const coreExtraFiles: Array<{ type?: string; path?: string }> =
    rpConfig.packages?.[`plugins/${CORE_PLUGIN_NAME}`]?.["extra-files"] ?? [];

  test("docs/index.html is a generic extra-file of the core package", () => {
    const entry = coreExtraFiles.find(
      // leading "/" makes the path repo-root-relative, not package-relative
      (f) => f.path === "/docs/index.html",
    );
    expect(entry).toBeDefined();
    expect(entry?.type).toBe("generic");
  });

  test("the x-release-please-version annotation is on the version line", () => {
    const versionLine = indexHtml
      .split("\n")
      .find((l) => /data-stat="version"/.test(l));
    expect(versionLine).toBeDefined();
    // Same line, or release-please's generic updater silently skips the bump.
    expect(versionLine).toContain("x-release-please-version");
  });
});

// ---- multi-platform native packaging (Claude / Cursor / Codex) --------------

const cursorPluginJson = JSON.parse(
  readFileSync(path.join(PLUGIN, ".cursor-plugin/plugin.json"), "utf8"),
);
const codexPluginJson = JSON.parse(
  readFileSync(path.join(PLUGIN, ".codex-plugin/plugin.json"), "utf8"),
);
const codexMarketplace = JSON.parse(
  readFileSync(path.join(ROOT, ".agents/plugins/marketplace.json"), "utf8"),
);
const cursorMarketplace = JSON.parse(
  readFileSync(path.join(ROOT, ".cursor-plugin/marketplace.json"), "utf8"),
);
const cursorHooks = JSON.parse(
  readFileSync(path.join(PLUGIN, "hooks/hooks-cursor.json"), "utf8"),
);
const codexHooks = JSON.parse(
  readFileSync(path.join(PLUGIN, "hooks/hooks-codex.json"), "utf8"),
);

const SAFETY_HOOK_SCRIPTS = [
  "block-no-verify.py",
  "prevent-main-commit.py",
  "block-slack-webhook.py",
  "block-db-push.py",
] as const;

function scriptPathsFromCursorHooks(hooks: {
  hooks?: Record<string, Array<{ command?: string; failClosed?: boolean }>>;
}): string[] {
  const out: string[] = [];
  for (const entries of Object.values(hooks.hooks ?? {})) {
    for (const entry of entries) {
      const cmd = entry.command ?? "";
      const match = cmd.match(/^python3 \.\/scripts\/([A-Za-z0-9_-]+\.py)$/);
      if (!match) throw new Error(`Invalid Cursor hook command: ${cmd}`);
      out.push(match[1]);
    }
  }
  return out;
}

function scriptPathsFromCodexHooks(hooks: {
  hooks?: Record<string, Array<{ hooks?: Array<{ command?: string }> }>>;
}): string[] {
  const out: string[] = [];
  for (const groups of Object.values(hooks.hooks ?? {})) {
    for (const group of groups) {
      for (const hook of group.hooks ?? []) {
        const cmd = hook.command ?? "";
        const match = cmd.match(
          /^python3 \$\{PLUGIN_ROOT\}\/scripts\/([A-Za-z0-9_-]+\.py)$/,
        );
        if (!match) throw new Error(`Invalid Codex hook command: ${cmd}`);
        out.push(match[1]);
      }
    }
  }
  return out;
}

describe("multi-platform packaging parity", () => {
  test("Claude / Cursor / Codex plugin versions match", () => {
    expect(cursorPluginJson.version).toBe(pluginJson.version);
    expect(codexPluginJson.version).toBe(pluginJson.version);
  });

  test("Cursor manifest wires skills, agents, hooks, MCP", () => {
    expect(cursorPluginJson.skills).toBe("./skills/");
    expect(cursorPluginJson.agents).toBe("./agents/");
    expect(cursorPluginJson.hooks).toBe("./hooks/hooks-cursor.json");
    expect(cursorPluginJson.mcpServers).toBe(".mcp.json");
    expect(cursorPluginJson.description).toContain(`${counts.agents} agents`);
    expect(cursorPluginJson.description).toContain(`${counts.skills} workflow skills`);
  });

  test("Codex manifest wires skills, MCP, hooks", () => {
    expect(codexPluginJson.skills).toBe("./skills/");
    expect(codexPluginJson.mcpServers).toBe("./.mcp.json");
    expect(codexPluginJson.hooks).toBe("./hooks/hooks-codex.json");
    expect(codexPluginJson.interface?.displayName).toBeTruthy();
  });

  test("manifest component paths resolve inside the plugin", () => {
    const cursorPaths = ["skills", "agents", "hooks", "mcpServers"];
    const codexPaths = ["skills", "hooks", "mcpServers"];
    for (const field of cursorPaths) {
      expect(existsSync(path.resolve(PLUGIN, cursorPluginJson[field]))).toBe(
        true,
      );
    }
    for (const field of codexPaths) {
      expect(codexPluginJson[field]).toStartWith("./");
      expect(existsSync(path.resolve(PLUGIN, codexPluginJson[field]))).toBe(
        true,
      );
    }
  });

  test("required packaging files exist", () => {
    const required = [
      path.join(PLUGIN, ".claude-plugin/plugin.json"),
      path.join(PLUGIN, ".cursor-plugin/plugin.json"),
      path.join(PLUGIN, ".codex-plugin/plugin.json"),
      path.join(PLUGIN, ".mcp.json"),
      path.join(PLUGIN, "hooks/hooks-cursor.json"),
      path.join(PLUGIN, "hooks/hooks-codex.json"),
      path.join(PLUGIN, "scripts/hook_payload.py"),
      path.join(PLUGIN, "scripts/HOOKS.md"),
      path.join(ROOT, ".cursor-plugin/marketplace.json"),
      path.join(ROOT, ".agents/plugins/marketplace.json"),
      path.join(ROOT, ".claude-plugin/marketplace.json"),
    ];
    for (const file of required) {
      expect(existsSync(file)).toBe(true);
    }
  });

  test("Codex marketplace points at the plugin", () => {
    const entry = codexMarketplace.plugins.find(
      (p: { name: string }) => p.name === CORE_PLUGIN_NAME,
    );
    expect(entry).toBeDefined();
    expect(entry?.source?.path ?? entry?.source).toContain(
      "plugins/agentic-engineering",
    );
    expect(path.resolve(ROOT, entry.source.path)).toBe(PLUGIN);
  });

  test("Cursor marketplace points at the nested plugin", () => {
    const entry = cursorMarketplace.plugins.find(
      (p: { name: string }) => p.name === CORE_PLUGIN_NAME,
    );
    expect(entry).toBeDefined();
    expect(
      path.resolve(ROOT, cursorMarketplace.metadata.pluginRoot, entry.source),
    ).toBe(PLUGIN);
  });

  test("Cursor + Codex hook configs reference existing safety scripts", () => {
    const cursorScripts = new Set(scriptPathsFromCursorHooks(cursorHooks));
    const codexScripts = new Set(scriptPathsFromCodexHooks(codexHooks));
    for (const script of SAFETY_HOOK_SCRIPTS) {
      expect(cursorScripts.has(script)).toBe(true);
      expect(codexScripts.has(script)).toBe(true);
      expect(existsSync(path.join(PLUGIN, "scripts", script))).toBe(true);
    }
  });

  test("Cursor security hooks fail closed", () => {
    const entries = Object.values(
      cursorHooks.hooks as Record<
        string,
        Array<{ command: string; failClosed?: boolean }>
      >,
    ).flat();
    expect(entries.length).toBeGreaterThan(0);
    for (const entry of entries) {
      expect(entry.failClosed).toBe(true);
    }
  });

  test("README uses native platform install and invocation contracts", () => {
    expect(rootReadme).toContain(
      "/add-plugin agentic-engineering@https://github.com/Life-With-Data/agentic-engineering",
    );
    expect(rootReadme).toContain("~/.cursor/plugins/local/agentic-engineering");
    expect(rootReadme).toContain(
      "codex plugin add agentic-engineering --marketplace agentic-engineering",
    );
    expect(rootReadme).not.toContain(
      "codex plugin install agentic-engineering",
    );
    expect(rootReadme).toContain("**`$wf-setup`**");
    expect(rootReadme).toContain("select `wf-setup` through `/skills`");
  });

  test("HOOKS.md documents the four shipped safety hooks", () => {
    const hooksMd = readFileSync(path.join(PLUGIN, "scripts/HOOKS.md"), "utf8");
    for (const script of SAFETY_HOOK_SCRIPTS) {
      expect(hooksMd).toContain(script);
      expect(hooksMd).toMatch(
        new RegExp(`${script.replace(".", "\\.")}.*Ships`, "s"),
      );
    }
  });
});

// ---- every component is documented in the plugin README ---------------------

describe("plugin README documents every agent", () => {
  test.each(agentFiles.map((f) => path.basename(f, ".md")))(
    "%s is in README",
    (slug) => {
      expect(pluginReadme).toContain(slug);
    },
  );
});

describe("plugin README documents every skill", () => {
  test.each(skillDirs)("%s is in README", (slug) => {
    expect(pluginReadme).toContain(slug);
  });
});

// ---- frontmatter hygiene ----------------------------------------------------

describe("agents declare name + description", () => {
  test.each(agentFiles.map((f) => [path.relative(PLUGIN, f), f] as const))(
    "%s",
    (_rel, file) => {
      const { data } = parseFrontmatter(readFileSync(file, "utf8"));
      expect(typeof data.name).toBe("string");
      expect(String(data.name).length).toBeGreaterThan(0);
      expect(typeof data.description).toBe("string");
      expect(String(data.description).length).toBeGreaterThan(0);
    },
  );
});

describe("skills declare name (matching dir) + description", () => {
  test.each(skillDirs)("%s/SKILL.md", (dir) => {
    const { data } = parseFrontmatter(
      readFileSync(path.join(PLUGIN, "skills", dir, "SKILL.md"), "utf8"),
    );
    expect(data.name).toBe(dir);
    expect(typeof data.description).toBe("string");
    expect(String(data.description).length).toBeGreaterThan(0);
  });
});

// ---- non-core plugins: basic consistency checks ------------------------------
// Every plugin under plugins/ other than the core one gets at minimum: a
// marketplace.json entry, an accurate "Includes N skill(s)" phrase in both
// descriptions, version parity, and skill frontmatter hygiene.

describe.each(nonCorePlugins)("non-core plugin: %s", (name) => {
  const dir = path.join(PLUGINS_DIR, name);
  const pj = JSON.parse(
    readFileSync(path.join(dir, ".claude-plugin/plugin.json"), "utf8"),
  );
  const entry = marketplace.plugins.find(
    (p: { name: string }) => p.name === name,
  );
  const skills = skillDirsIn(dir);
  const skillPhrase = `Includes ${skills.length} skill${skills.length === 1 ? "" : "s"}`;

  test("has a marketplace.json entry", () => {
    expect(entry).toBeDefined();
  });

  test(`plugin.json description declares "${skillPhrase}"`, () => {
    expect(pj.description).toContain(skillPhrase);
  });

  test(`marketplace.json description declares "${skillPhrase}"`, () => {
    expect(entry?.description).toContain(skillPhrase);
  });

  test("plugin.json and marketplace.json versions agree", () => {
    expect(pj.version).toBe(entry?.version);
  });

  if (skills.length) {
    test.each(skills)(
      "skill %s declares name (matching dir) + description",
      (skillDir) => {
        const { data } = parseFrontmatter(
          readFileSync(path.join(dir, "skills", skillDir, "SKILL.md"), "utf8"),
        );
        expect(data.name).toBe(skillDir);
        expect(typeof data.description).toBe("string");
        expect(String(data.description).length).toBeGreaterThan(0);
      },
    );
  }
});
