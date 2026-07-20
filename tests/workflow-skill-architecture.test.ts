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
    "brainstorming", "deepen-plan", "interview-me", "land-plan-docs",
    "report-bug", "reproduce-bug", "triage", "workflows-brainstorm",
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
    "config-flags", "install-hooks", "lifecycle", "lifecycle-doctor", "setup",
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
});
