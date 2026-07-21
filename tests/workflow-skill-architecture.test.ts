import { describe, expect, test } from "bun:test";
import {
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
} from "fs";
import path from "path";
import { parseFrontmatter } from "../src/utils/frontmatter";

const ROOT = path.resolve(import.meta.dir, "..");
const PLUGIN = path.join(ROOT, "plugins", "agentic-engineering");
const SKILLS = path.join(PLUGIN, "skills");

const WORKFLOW_REFERENCES: Record<string, string[]> = {
  "wf-grooming": [
    "brainstorming", "deepen-plan", "interview-me", "report-bug",
    "reproduce-bug", "triage", "workflows-brainstorm",
    "workflows-groom", "workflows-plan",
  ],
  "wf-development": [
    "agent-native-architecture", "api-and-interface-design",
    "debugging-and-error-recovery", "frontend-design", "git-worktree",
    "observability-and-instrumentation", "resolve-parallel",
    "workflows-orchestrate", "workflows-work",
  ],
  "wf-testing": [
    "test-browser", "test-driven-development", "test-strategy-reviewer",
    "verification-loop",
  ],
  "wf-review": [
    "agent-native-audit", "doubt-driven-development", "resolve-pr-parallel",
    "security-and-hardening", "workflows-review",
  ],
  "wf-delivery": [
    "changelog", "ci-resolve-workflow-issues", "land-pr", "workflows-merge",
  ],
  "wf-documentation": [
    "compound-docs", "deploy-docs", "document-review", "land-docs",
    "reflect-for-skill-updates", "workflows-compound",
  ],
  "wf-setup": [
    "config-flags", "install-hooks", "lifecycle", "lifecycle-bootstrap",
    "lifecycle-doctor", "setup",
  ],
};

const CAPABILITIES = [
  "repository-overview",
  "development-environment",
  "test-execution",
  "bug-reproduction",
  "observability",
  "data-operations",
  "infrastructure-operations",
  "delivery",
  "security-and-access",
  "documentation",
];

const SCRIPT_BUNDLES: Record<string, Record<string, string>> = {
  "wf-grooming": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
  },
  "wf-development": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "workflow-repo-preflight.py": "scripts/workflow-repo-preflight.py",
    "worktree-manager.sh": "skills/wf-development/scripts/worktree-manager.sh",
  },
  "wf-testing": {
    "repository-context.py": "scripts/repository-context.py",
  },
  "wf-review": {
    "repository-context.py": "scripts/repository-context.py",
    "get-pr-comments": "skills/wf-review/scripts/get-pr-comments",
    "resolve-pr-thread": "skills/wf-review/scripts/resolve-pr-thread",
  },
  "wf-delivery": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "pr-landable-status": "skills/wf-delivery/scripts/pr-landable-status",
    "worktree-manager.sh": "skills/wf-development/scripts/worktree-manager.sh",
  },
  "wf-documentation": {
    "repository-context.py": "scripts/repository-context.py",
  },
  "wf-setup": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "bootstrap_lifecycle_board.py": "scripts/bootstrap_lifecycle_board.py",
    "config_registry.py": "scripts/config_registry.py",
    "block-db-push.py": "scripts/block-db-push.py",
    "block-no-verify.py": "scripts/block-no-verify.py",
    "block-slack-webhook.py": "scripts/block-slack-webhook.py",
    "hook_payload.py": "scripts/hook_payload.py",
    "prevent-main-commit.py": "scripts/prevent-main-commit.py",
  },
};

function recursiveFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...recursiveFiles(target));
    else files.push(target);
  }
  return files;
}

describe("workflow skill architecture", () => {
  test("the public skill set is fixed at seven wf-* routers", () => {
    const actual = readdirSync(SKILLS, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();
    expect(actual).toEqual(Object.keys(WORKFLOW_REFERENCES).sort());
  });

  test("only router entry points are discoverable skills", () => {
    const actual = recursiveFiles(SKILLS)
      .filter((file) => path.basename(file) === "SKILL.md")
      .map((file) => path.relative(SKILLS, file))
      .sort();
    const expected = Object.keys(WORKFLOW_REFERENCES)
      .map((name) => path.join(name, "SKILL.md"))
      .sort();
    expect(actual).toEqual(expected);
  });

  test("every router declares an unambiguous workflow boundary", () => {
    for (const name of Object.keys(WORKFLOW_REFERENCES)) {
      const source = readFileSync(path.join(SKILLS, name, "SKILL.md"), "utf8");
      const { data } = parseFrontmatter(source);
      expect(data.name).toBe(name);
      expect(String(data.description)).toContain("Workflow policy");
      expect(source).toContain("Layer: Workflow policy");
      expect(source).toContain("Requires repository capabilities:");
      expect(source).toContain("Does not contain:");
      expect(source).toContain("## Wrong-layer recovery");
      expect(source).toContain("repository-context.py");
    }
  });

  test("retained modules are flat references, not nested skills", () => {
    for (const [owner, expected] of Object.entries(WORKFLOW_REFERENCES)) {
      const references = path.join(SKILLS, owner, "references");
      for (const module of expected) {
        expect(existsSync(path.join(references, `${module}.md`))).toBe(true);
      }

      for (const entry of readdirSync(references, { withFileTypes: true })) {
        expect(entry.isFile()).toBe(true);
        if (entry.name.endsWith(".md")) {
          const source = readFileSync(path.join(references, entry.name), "utf8");
          expect(source.startsWith("---\n")).toBe(false);
        }
      }

      for (const resource of ["scripts", "assets"]) {
        const directory = path.join(SKILLS, owner, resource);
        if (!existsSync(directory)) continue;
        for (const entry of readdirSync(directory, { withFileTypes: true })) {
          expect(entry.isFile()).toBe(true);
        }
      }
    }
  });

  test("every executable dependency is bundled with its consuming skill", () => {
    for (const [owner, expected] of Object.entries(SCRIPT_BUNDLES)) {
      const scriptDirectory = path.join(SKILLS, owner, "scripts");
      expect(readdirSync(scriptDirectory).sort()).toEqual(Object.keys(expected).sort());

      for (const [file, canonical] of Object.entries(expected)) {
        expect(readFileSync(path.join(scriptDirectory, file), "utf8")).toBe(
          readFileSync(path.join(PLUGIN, canonical), "utf8"),
        );
      }
    }
  });

  test("skill instructions resolve scripts locally, never through a plugin root", () => {
    const source = recursiveFiles(SKILLS)
      .filter((file) => file.endsWith(".md"))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    expect(source).not.toContain("CLAUDE_PLUGIN_ROOT");
    expect(source).not.toContain("PLUGIN_ROOT");
    expect(source).not.toContain("<plugin-path>");
  });

  test("active workflow instructions do not invoke retired flat skills", () => {
    const sources = [
      ...recursiveFiles(SKILLS).filter((file) => file.endsWith(".md")),
      ...recursiveFiles(path.join(PLUGIN, "agents")).filter((file) => file.endsWith(".md")),
      path.join(PLUGIN, "README.md"),
    ];
    const retiredSlashNames = [
      "workflows-brainstorm", "workflows-compound", "workflows-groom",
      "workflows-merge", "workflows-orchestrate", "workflows-plan",
      "workflows-review", "workflows-work", "reproduce-bug", "report-bug",
      "triage", "lifecycle-doctor", "config-flags",
    ];
    const stale: string[] = [];

    for (const file of sources) {
      const source = readFileSync(file, "utf8");
      for (const name of retiredSlashNames) {
        const pattern = "(^|[\\s'\"(]|`)/" + name + "\\b";
        if (new RegExp(pattern, "m").test(source)) {
          stale.push(`${path.relative(ROOT, file)} invokes /${name}`);
        }
      }
    }

    expect(stale).toEqual([]);
  });

  test("agents request capabilities without assuming retired skill names or layouts", () => {
    const source = recursiveFiles(path.join(PLUGIN, "agents"))
      .filter((file) => file.endsWith(".md"))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    for (const stale of [
      "agent-browser",
      "~/.claude/skills",
      ".claude/skills/",
      "docs/plans/",
      "todos/*.md",
    ]) {
      expect(source).not.toContain(stale);
    }
  });

  test("plugin skills do not prescribe consumer skill layouts", () => {
    const source = recursiveFiles(SKILLS)
      .filter((file) => statSync(file).isFile())
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    expect(source).not.toContain("~/.claude/skills");
    expect(source).not.toContain(".claude/skills/");
    expect(source).not.toContain(".agents/skills/");
    expect(source).not.toContain("wf-maintenance");
  });

  test("local resource links survive the consolidated layout", () => {
    const broken: string[] = [];
    for (const file of recursiveFiles(SKILLS).filter((item) => item.endsWith(".md"))) {
      const source = readFileSync(file, "utf8").replace(/```[\s\S]*?```/g, "");
      for (const match of source.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
        const raw = match[1].trim();
        if (/^(?:[a-z]+:|#)/i.test(raw) || raw.includes("<")) continue;
        const target = raw.split("#", 1)[0];
        if (!target) continue;
        if (!existsSync(path.resolve(path.dirname(file), target))) {
          broken.push(`${path.relative(ROOT, file)} -> ${raw}`);
        }
      }
    }
    expect(broken).toEqual([]);
  });

  test("active planning is issue-canonical and has no plan-only landing machinery", () => {
    expect(existsSync(path.join(
      SKILLS, "wf-grooming", "references", "land-plan-docs.md",
    ))).toBe(false);
    expect(existsSync(path.join(PLUGIN, "scripts", "plan-tracker-guard.py"))).toBe(false);

    const pluginManifest = readFileSync(
      path.join(PLUGIN, ".claude-plugin", "plugin.json"),
      "utf8",
    );
    expect(pluginManifest).not.toContain("plan-tracker-guard.py");

    const activePlanning = [
      path.join(SKILLS, "wf-grooming", "SKILL.md"),
      ...recursiveFiles(path.join(SKILLS, "wf-grooming", "references"))
        .filter((file) => file.endsWith(".md")),
      path.join(SKILLS, "wf-development", "references", "workflows-work.md"),
      path.join(SKILLS, "wf-setup", "references", "lifecycle.md"),
      path.join(PLUGIN, "README.md"),
      path.join(PLUGIN, "FLOWS.md"),
      path.join(PLUGIN, "WORKFLOW_SKILLS.md"),
      path.join(ROOT, "README.md"),
    ].map((file) => readFileSync(file, "utf8")).join("\n");

    expect(activePlanning).not.toContain("github_issue:");
    expect(activePlanning).not.toContain("join-keyed plan doc");
    expect(activePlanning).not.toContain("land-plan-docs");
    expect(activePlanning).toContain("--materialize-packet <N>");

    const planningRoute = readFileSync(
      path.join(SKILLS, "wf-grooming", "references", "workflows-plan.md"),
      "utf8",
    );
    expect(planningRoute).toContain("--gate plan");
    expect(planningRoute).toContain("If `provenance` is `untrusted`");
    expect(planningRoute).toContain("--decompose");
    expect(planningRoute).toContain("--groom-verify");
    expect(planningRoute).toContain("finally/trap");
    expect(planningRoute).toContain("--materialize-packet <parent>");

    const publicWorkflowDocs = [
      path.join(PLUGIN, "README.md"),
      path.join(PLUGIN, "FLOWS.md"),
      path.join(PLUGIN, "WORKFLOW_SKILLS.md"),
      path.join(ROOT, "README.md"),
    ].map((file) => readFileSync(file, "utf8")).join("\n");
    expect(publicWorkflowDocs).not.toMatch(/\b(?:shipped|deployed|compounded)\b/);

    const lifecycle = readFileSync(
      path.join(SKILLS, "wf-setup", "references", "lifecycle.md"),
      "utf8",
    );
    const statuses = [
      "stub", "brainstormed", "planned", "in_progress", "in_review", "done", "abandoned",
    ];
    expect(lifecycle).toContain("## The 7 Status values");
    statuses.forEach((status, index) => {
      expect(lifecycle).toContain(`${index + 1}. \`${status}\``);
    });
  });

  test("setup exposes a complete and strict lifecycle adoption journey", () => {
    const setupRouter = readFileSync(
      path.join(SKILLS, "wf-setup", "SKILL.md"),
      "utf8",
    );
    const setupFlow = readFileSync(
      path.join(SKILLS, "wf-setup", "references", "setup.md"),
      "utf8",
    );
    const bootstrap = readFileSync(
      path.join(SKILLS, "wf-setup", "references", "lifecycle-bootstrap.md"),
      "utf8",
    );
    const doctor = readFileSync(
      path.join(SKILLS, "wf-setup", "references", "lifecycle-doctor.md"),
      "utf8",
    );

    expect(setupRouter).toContain("references/lifecycle-bootstrap.md");
    expect(setupFlow).toContain("lifecycle-bootstrap.md");
    expect(bootstrap).toContain(
      'python3 "<skill-directory>/scripts/bootstrap_lifecycle_board.py"',
    );
    for (const binding of ["workflow-only", "auto-add", "none"]) {
      expect(bootstrap).toContain(`\`${binding}\``);
    }
    expect(bootstrap).toContain("gh auth refresh --hostname github.com --scopes project");
    expect(bootstrap).toContain("git config agentic.trustedBoardOwners");
    expect(bootstrap).toContain("ADD_TO_PROJECT_PAT");
    expect(bootstrap).toContain("Projects: Read and write");
    expect(bootstrap).toContain("--backfill");
    expect(bootstrap).toContain("--doctor");
    expect(bootstrap).toContain("--probe-only");
    expect(bootstrap).toContain("status:planned no:assignee");
    expect(bootstrap).toContain("default branch");
    expect(bootstrap).toContain("doctor `--live`");

    const setupDocs = [setupRouter, setupFlow, bootstrap, doctor].join("\n");
    expect(setupDocs).not.toContain("Phase 4");
    expect(doctor).toContain("item_closed_workflow");
    expect(doctor).toContain("board_write_access");
    expect(doctor).toContain("missing Priority field");
    expect(doctor).toContain("missing canonical repository");
    expect(doctor).toContain("missing board");
    expect(doctor).toContain("overrides an earlier read-only");
    expect(doctor).toContain("must not add the issue directly first");
    expect(doctor).toContain("Permanent issue deletion");
    expect(doctor).toContain("is not attempted");
    expect(doctor).toContain("removal/verification overrides");
    expect(doctor).toContain("Ready for first work item: no");
  });

  test("this repository has one explicitly local operational skill", () => {
    const localSkills = path.join(ROOT, ".agents", "skills");
    const entries = readdirSync(localSkills, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
    expect(entries).toEqual(["agentic-engineering-repository"]);

    const source = readFileSync(
      path.join(localSkills, "agentic-engineering-repository", "SKILL.md"),
      "utf8",
    );
    expect(source).toContain("Scope: This repository only");
    expect(source).toContain("Never apply these mechanics to a consumer repository");
  });

  test("the root contract declares every fixed capability", () => {
    const agents = readFileSync(path.join(ROOT, "AGENTS.md"), "utf8");
    expect(agents).toContain("## Agentic Engineering Repository Contract");
    expect(agents).toContain("contract-version: 2");
    for (const capability of CAPABILITIES) {
      expect(agents).toMatch(new RegExp(`^- ${capability}:`, "m"));
    }
  });

  test("Claude Code imports the tool-agnostic root instructions first", () => {
    const claude = readFileSync(path.join(ROOT, "CLAUDE.md"), "utf8");
    expect(claude.split(/\r?\n/, 1)[0]).toBe("@AGENTS.md");
  });
});
