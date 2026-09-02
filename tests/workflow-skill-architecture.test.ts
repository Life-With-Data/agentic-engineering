import { describe, expect, test } from "bun:test";
import {
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
} from "fs";
import path from "path";
import { SCRIPT_BUNDLES } from "../scripts/script-bundles";
import { parseFrontmatter } from "../src/utils/frontmatter";

const ROOT = path.resolve(import.meta.dir, "..");
const PLUGIN = path.join(ROOT, "plugins", "agentic-engineering");
const SKILLS = path.join(PLUGIN, "skills");

const WORKFLOW_REFERENCES: Record<string, string[]> = {
  "wf-orchestrate": [
    "escalation-contract", "orchestrate", "subagent-delegation",
  ],
  "wf-auto": ["auto-run"],
  "wf-grooming": [
    "brainstorming", "deepen-plan", "design-context", "interview-me",
    "report-bug", "reproduce-bug", "triage", "workflows-brainstorm",
    "workflows-groom", "workflows-plan",
  ],
  "wf-development": [
    "api-and-interface-design",
    "debugging-and-error-recovery",
    "git-worktree", "observability-and-instrumentation",
    "workflows-work",
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
    "changelog", "ci-resolve-workflow-issues", "land-pr",
  ],
  "wf-documentation": [
    "compound-docs", "document-review", "land-docs",
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

// The bundle map (which skill vendors which canonical script) lives in
// scripts/script-bundles.ts, shared with the mechanical fixer
// scripts/sync-skill-scripts.ts so the gate and the tool can never drift.

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
  test("the public skill set is fixed at nine wf-* routers", () => {
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
        expect(
          readFileSync(path.join(scriptDirectory, file), "utf8"),
          `${owner}/scripts/${file} out of sync with canonical ${canonical} — run \`bun run skills:sync\``,
        ).toBe(readFileSync(path.join(PLUGIN, canonical), "utf8"));
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

  test("fragment links between skill references resolve to a real heading", () => {
    // A policy pointer ("see workflows-review Findings") is only as good as
    // the heading it names. The escalation contract once cited an orchestrate
    // section that had been deleted, and nothing failed. Resolve every
    // #fragment the way GitHub does and demand the heading exists.
    const slug = (heading: string) =>
      heading
        .replace(/`/g, "")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .toLowerCase()
        .trim()
        .replace(/[^\w\s-]/g, "")
        .replace(/ /g, "-");
    const headings = new Map<string, Set<string>>();
    const headingsOf = (file: string) => {
      let found = headings.get(file);
      if (!found) {
        const source = readFileSync(file, "utf8").replace(/```[\s\S]*?```/g, "");
        found = new Set(
          [...source.matchAll(/^#{1,6}\s+(.+?)\s*$/gm)].map((m) => slug(m[1])),
        );
        headings.set(file, found);
      }
      return found;
    };
    const dangling: string[] = [];
    for (const file of recursiveFiles(SKILLS).filter((item) => item.endsWith(".md"))) {
      const source = readFileSync(file, "utf8").replace(/```[\s\S]*?```/g, "");
      for (const match of source.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
        const raw = match[1].trim();
        if (/^[a-z]+:/i.test(raw) || raw.includes("<") || !raw.includes("#")) continue;
        const [target, fragment] = raw.split("#", 2);
        const resolved = target ? path.resolve(path.dirname(file), target) : file;
        if (!existsSync(resolved)) continue; // the test above reports these
        if (!headingsOf(resolved).has(fragment)) {
          dangling.push(`${path.relative(ROOT, file)} -> ${raw}`);
        }
      }
    }
    expect(dangling).toEqual([]);
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
    expect(planningRoute).toContain("Status = planned");

    // Guardrail (issue #300): the posture decision this file documents beside
    // complexity assessment must keep referencing the posture spec field and
    // the --groom-verify posture surface, by category token, never a frozen
    // sentence (see docs/solutions/testing-patterns/
    // grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md).
    expect(planningRoute).toContain("`posture`");
    expect(planningRoute).toContain("parent_posture");
    // Issue #401: autonomous is the default; the route documents the opt-out
    // label write and the fused hands_off read, never a repo-default tier.
    expect(planningRoute).toContain("posture: standard");
    expect(planningRoute).toContain("hands_off");
    expect(planningRoute).not.toContain("delivery_mode");
    expect(planningRoute).not.toContain("posture_source");
    // Issues #389/#401: the posture step is non-interactive — no offer, no
    // question (whitespace-normalized so a reflow across the hard wrap does
    // not false-fail/false-pass).
    const flowPlanning = planningRoute.replace(/\s+/g, " ");
    expect(flowPlanning).toContain("non-interactive");
    expect(flowPlanning).not.toContain("proactively offer");

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
      "stub", "brainstormed", "planned", "ready_for_work", "in_progress", "in_review", "done", "abandoned",
    ];
    expect(lifecycle).toContain("## The 8 Status values");
    statuses.forEach((status, index) => {
      expect(lifecycle).toContain(`${index + 1}. \`${status}\``);
    });
  });

  test("the unattended entry point keeps zero structural gates", () => {
    const auto = [
      path.join(SKILLS, "wf-auto", "SKILL.md"),
      path.join(SKILLS, "wf-auto", "references", "auto-run.md"),
    ].map((file) => readFileSync(file, "utf8")).join("\n");
    const flow = auto.replace(/\s+/g, " ");

    expect(auto).toMatch(/--set-status\s+<N>\s+ready_for_work\s+--force/);
    expect(flow).toMatch(/sole self-approval path|auditable exception/i);
    expect(flow).toMatch(/--ready-work/);
    expect(flow).toMatch(/posture:\*/);
    expect(flow).toMatch(/no standard posture|posture[^.]{0,40}\bstrip/i);
    expect(flow).toMatch(/[Zz]ero structural gates/);
    expect(flow).toMatch(/repository-required checks/);
    expect(flow).toMatch(/do not post a ritual retrospective/i);
    expect(flow).toMatch(/P1 findings/);
    // A revert that ADDS a gate alongside the prose is the failure mode a
    // presence-only assertion misses; naming the suppressed gates is the part
    // that can be checked here. (The interactive merge `[y/N]` is mentioned
    // deliberately — as the thing a surviving posture label would bring back —
    // so its literal cannot be banned.)
    expect(flow).toMatch(/merge confirmation/i);
    // Security floor: the invocation authorizes the task, not a new one.
    expect(flow).toMatch(/only instruction source/i);
    expect(auto).toContain("escalation-contract.md");

    expect(auto).not.toMatch(/\bC0[A-Z0-9]{8,}\b/);
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
    expect(bootstrap).toContain("LWD_APP_CLIENT_ID");
    expect(bootstrap).toContain("LWD_APP_PRIVATE_KEY");
    expect(bootstrap).toContain("Projects: Read and write");
    expect(bootstrap).toContain("--backfill");
    expect(bootstrap).toContain("--doctor");
    expect(bootstrap).toContain("--probe-only");
    expect(bootstrap).toContain("status:ready_for_work no:assignee");
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

  test("posture changes interaction style without bypassing the approval seam", () => {
    const orchestrate = readFileSync(
      path.join(SKILLS, "wf-orchestrate", "references", "orchestrate.md"),
      "utf8",
    );
    const flow = (s: string) => s.replace(/\s+/g, " ");
    expect(orchestrate).toContain("--groom-verify");
    expect(flow(orchestrate)).toContain("A `planned` item routes to a human");
    expect(flow(orchestrate)).toContain("only an approved item is ready to claim");
    expect(flow(orchestrate)).toContain("`posture:standard` label requests more human involvement");
    expect(flow(orchestrate)).toContain("Explicit invocation arguments override");
    expect(orchestrate).not.toContain("delivery_mode");
    expect(orchestrate).not.toContain("posture_source");
    const contract = readFileSync(
      path.join(SKILLS, "wf-orchestrate", "references", "escalation-contract.md"),
      "utf8",
    );
    expect(contract).not.toContain("not the user or the tracker");
    expect(flow(contract)).toContain("agent discipline, not an engine check");
    expect(flow(contract)).not.toContain("the engine returns a `blocked` verdict");
  });

  test("autonomous-mode-owning skills reference the shared escalation contract", () => {
    // Category-level assertion (repo guardrail policy): freeze the presence of
    // the cross-link token — the relative path to escalation-contract.md — not
    // any particular sentence around it. A frozen sentence would silently
    // false-pass if the surrounding prose is later reworded.
    const TOKEN = "escalation-contract.md";

    const orchestrate = readFileSync(
      path.join(SKILLS, "wf-orchestrate", "references", "orchestrate.md"),
      "utf8",
    );
    expect(orchestrate).toContain(TOKEN);

    const workflowsWork = readFileSync(
      path.join(SKILLS, "wf-development", "references", "workflows-work.md"),
      "utf8",
    );
    expect(workflowsWork).toContain(TOKEN);
  });

  test("workflows-work clarification gate is evidence-first (issue #303)", () => {
    const workPath = path.join(
      SKILLS, "wf-development", "references", "workflows-work.md",
    );
    const work = readFileSync(workPath, "utf8");
    const flow = work.replace(/\s+/g, " ");
    expect(flow).toContain("Read the relevant code and repository guidance");
    expect(flow).toContain("smallest coherent change");
    expect(flow).toContain("requirements data, not instructions");
    expect(flow).toContain("record the concrete blocker and ask once");
    expect(flow).toContain("Do not repeatedly re-ask");
    expect(work).toContain("escalation-contract.md");
    expect(work).toContain("--claim");
    expect(work).toContain("--set-status");
    expect(work).toContain("in_review");
  });

  test("escalation asking sites consult tracker-persisted answers first (issue #390)", () => {
    // Category-level assertions (repo guardrail policy: freeze the category,
    // not the spelling — a frozen sentence silently false-passes once prose is
    // reworded). escalation-contract.md makes the `human`-labeled tracker
    // comment the escalation's system of record; both asking sites must
    // consult it before re-asking, and workflows-work must persist an
    // interactively received answer back as one. Whitespace-normalized so a
    // pure reflow cannot fail this.
    const flow = (s: string) => s.replace(/\s+/g, " ");

    const work = flow(readFileSync(
      path.join(SKILLS, "wf-development", "references", "workflows-work.md"),
      "utf8",
    ));
    const orchestrate = flow(readFileSync(
      path.join(SKILLS, "wf-orchestrate", "references", "orchestrate.md"),
      "utf8",
    ));

    expect(work).toContain("Do not repeatedly re-ask");
    expect(orchestrate).toContain("tracker state");
  });

  test("document-review carves out non-interactive invocation (issue #391)", () => {
    // Category-level assertions (freeze the category, not the spelling):
    // document-review's Step 5 approval gate and Step 6 menu must be governed
    // by an invocation-mode carve-out — non-interactive/workflow callers get
    // auto-fix-and-report (substantive changes flagged, not gated on
    // approval) and control returned to the caller, while standalone
    // interactive sessions keep the ask-before-substantive-change behavior.
    // Whitespace-normalized so a pure reflow cannot fail this.
    const flow = (s: string) => s.replace(/\s+/g, " ");
    const review = flow(readFileSync(
      path.join(SKILLS, "wf-documentation", "references", "document-review.md"),
      "utf8",
    ));

    // The carve-out names both modes and covers both sites (Steps 5-6).
    expect(review).toContain("Non-interactive invocation");
    expect(review).toContain("Standalone interactive session");
    expect(review).toContain("both Step 5 and Step 6");

    // Non-interactive branch: auto-fix and report, substantive changes
    // flagged in the report rather than gated on approval, no menu, control
    // returned to the calling workflow.
    expect(review).toContain("do not pause for approval");
    expect(review).toContain("do not offer the Step 6 menu");
    expect(review).toContain("including substantive changes");
    expect(review).toContain("flagging substantive changes");
    expect(review).toContain("return control to the calling workflow");

    // Interactive behavior is unchanged: the Step 5 approval gate survives.
    expect(review).toContain("**Ask approval** before substantive changes");
  });

  test("orchestrate honors per-ticket delivery posture at the routing boundary", () => {
    const orchestratePath = path.join(
      SKILLS, "wf-orchestrate", "references", "orchestrate.md",
    );
    const orchestrate = readFileSync(orchestratePath, "utf8");
    const flow = orchestrate.replace(/\s+/g, " ");
    expect(orchestrate).toContain("--groom-verify <N>");
    expect(flow).toContain("A `planned` item routes to a human");
    expect(flow).toContain("`posture:standard` label requests more human involvement");
    expect(flow).toContain("Explicit invocation arguments override");
    expect(flow).toContain("only an approved item is ready to claim");
  });

  test("every agent name cited in skill prose resolves to a shipped agent", () => {
    // Regression guard: `linting-agent` shipped in workflows-work.md for the
    // life of the file while the actual agent was named `lint`, so an agent
    // following the instruction could not dispatch it. The valid set is DERIVED
    // from the agents tree on every run, never a frozen list of spellings
    // (docs/solutions/testing-patterns/
    // grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md).
    const shipped = new Set(
      recursiveFiles(path.join(PLUGIN, "agents"))
        .filter((file) => file.endsWith(".md"))
        .map((file) => path.basename(file, ".md")),
    );

    // Named in prose as an external component, not a dispatchable plugin agent.
    const THIRD_PARTY = new Set(["request-filtering-agent"]);

    // English compounds, not names: "sub-agent", "multi-agent". Excluded by the
    // bound prefix rather than by listing tokens, so a real agent name can
    // never be silently waived by landing on an allowlist.
    const GENERIC = /^(?:sub|multi|single|per|non|co|inter|intra|cross)-agent$/;

    const unresolved: string[] = [];
    for (const file of recursiveFiles(SKILLS).filter((f) => f.endsWith(".md"))) {
      const source = readFileSync(file, "utf8")
        .replace(/```[\s\S]*?```/g, "")   // fenced samples are illustrative
        .replace(/\]\([^)]*\)/g, "")      // link targets are paths, not agents
        .replace(/name="[^"]*"/g, "");    // XML pattern attributes in examples
      const where = path.relative(ROOT, file);

      // Arm 1: the canonical `<name>` agent citation form.
      for (const m of source.matchAll(/`([a-z0-9-]+)`\s+agent\b/g)) {
        if (!shipped.has(m[1])) unresolved.push(`${where} -> ${m[1]}`);
      }
      // Arm 2: bare `<something>-agent` tokens. This arm is what actually
      // catches the shipped defect, because `linting-agent` was unbackticked.
      for (const m of source.matchAll(/\b([a-z0-9]+(?:-[a-z0-9]+)*-agent)\b/g)) {
        const name = m[1];
        if (shipped.has(name) || THIRD_PARTY.has(name) || GENERIC.test(name)) continue;
        unresolved.push(`${where} -> ${name}`);
      }
    }

    expect(unresolved).toEqual([]);
  });

  test("skills do not instruct host primitives this plugin cannot rely on", () => {
    // Removal pin for the Swarm Mode block, which told the agent to call
    // Teammate({operation:"spawnTeam"}) and Task({team_name:...}) -- APIs that
    // do not exist, so following the route produced failing tool calls.
    //
    // Honest scope: a denylist pins THESE primitives out of the tree; it cannot
    // catch the next invented API. The control for that class is review, not
    // this test. Same shape as "active workflow instructions do not invoke
    // retired flat skills" above.
    const source = recursiveFiles(SKILLS)
      .filter((file) => file.endsWith(".md"))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");

    for (const primitive of [
      "Teammate(",
      "team_name",
      "spawnTeam",
      "requestShutdown",
    ]) {
      expect(source).not.toContain(primitive);
    }
  });

  test("grooming challenges scope before it is settled or persisted", () => {
    // The scope challenge is the only YAGNI force grooming has, and it lives in
    // prose -- so a future reword can delete the dispatch and grooming silently
    // returns to having no challenge at all, which is the state it was added to
    // fix, with nothing failing. The "every agent name cited in skill prose
    // resolves to a shipped agent" test above proves the name is real; it
    // cannot see the name go missing from these two files.
    //
    // Category-level per repo guardrail policy: assert the agent is dispatched
    // in the right SECTION of each route, never a frozen sentence.
    const AGENT = "scope-skeptic";

    const before = (source: string, heading: string) => {
      const end = source.indexOf(heading);
      // A renamed heading must fail loudly, not slice the whole file and pass.
      expect(end).toBeGreaterThan(-1);
      return source.slice(0, end);
    };

    // Groom route: challenged while resolving scope, before grooming completes.
    const groom = readFileSync(
      path.join(SKILLS, "wf-grooming", "references", "workflows-groom.md"),
      "utf8",
    );
    expect(before(groom, "## Completion")).toContain(AGENT);

    // Plan route: challenged against the drafted units, before the --decompose
    // write that is the readiness attestation. A ready request reaches planning
    // through the groom route gate without passing Resolve scope, so for that
    // item this dispatch is the only challenge it will ever get.
    const plan = readFileSync(
      path.join(SKILLS, "wf-grooming", "references", "workflows-plan.md"),
      "utf8",
    );
    const beforePersist = before(plan, "## Persist and track");
    expect(beforePersist).toContain(AGENT);

    // ...and carries a dedup condition, so covering both routes does not buy a
    // duplicate dispatch on unchanged scope. Concept tokens with slack between
    // them, not a pinned phrase.
    expect(beforePersist).toMatch(/\bskip\b[\s\S]{0,300}\balready\b/i);
  });

  test("grooming hands off with proceed-statements and throttles asks (issue #388)", () => {
    // Category-token assertions per repo guardrail policy: freeze the category,
    // never a frozen literal spelling (see docs/solutions/testing-patterns/
    // grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md).
    const references = path.join(SKILLS, "wf-grooming", "references");
    // Whitespace-normalized so a pure reflow of a sentence cannot fail this.
    const flow = (s: string) => s.replace(/\s+/g, " ");

    // 1. Handoff sites are proceed-statements, not menus. The pipeline order is
    // fixed, so the old AskUserQuestion-driven next-steps menu carried no
    // information; the handoff must announce the next stage and continue.
    const brainstormRoute = readFileSync(
      path.join(references, "workflows-brainstorm.md"),
      "utf8",
    );
    // Menu token gone: no next-steps menu presentation at the handoff.
    expect(brainstormRoute).not.toContain("present next steps");
    expect(brainstormRoute).not.toContain("What would you like to do next?");
    // Proceed-statement token present at BOTH former menu sites (Phase 4
    // handoff and the post-document-review continuation).
    const proceedMentions = flow(brainstormRoute).split("say stop to redirect").length - 1;
    expect(proceedMentions).toBeGreaterThanOrEqual(2);
    // The handoff phase itself no longer drives an AskUserQuestion menu.
    // (AskUserQuestion stays legitimate earlier, in the interview phases.)
    const handoffStart = brainstormRoute.indexOf("### Phase 4: Handoff");
    expect(handoffStart).toBeGreaterThan(-1);
    expect(brainstormRoute.slice(handoffStart)).not.toContain("AskUserQuestion");

    // The duplicate handoff menu in the brainstorming reference is also a
    // proceed-statement now. (Per-section validation pauses are untouched and
    // deliberately unasserted — they are in scope for validation, not handoff.)
    const brainstorming = readFileSync(
      path.join(references, "brainstorming.md"),
      "utf8",
    );
    const refHandoff = brainstorming.indexOf("### Phase 4: Handoff");
    expect(refHandoff).toBeGreaterThan(-1);
    expect(flow(brainstorming.slice(refHandoff))).toContain("say stop to redirect");
    // Same negative freeze as the primary site: the duplicate handoff cannot
    // regrow a menu — no AskUserQuestion drive and no options-menu token may
    // coexist with the proceed-statement (review hardening from issue #388).
    expect(brainstorming.slice(refHandoff)).not.toContain("AskUserQuestion");
    expect(brainstorming).not.toContain("Present clear options");

    // 2. The groom route's ask throttle carries the default-and-note rule:
    // resolvable scope questions get a recorded default, revisable at the
    // human's ready_for_work stamp, instead of an ask.
    const groom = readFileSync(
      path.join(references, "workflows-groom.md"),
      "utf8",
    );
    expect(groom).toContain("Default-and-note");
    expect(groom).toContain("ready_for_work");

    // 3. Triage no longer asks for priority — it is estimated and recorded
    // without asking (aligned with workflows-plan.md's no-ask priority rule);
    // asks are reserved for product-scope judgment.
    const triage = readFileSync(path.join(references, "triage.md"), "utf8");
    expect(triage).not.toContain("Ask for a decision when priority");
    expect(triage.replace(/\s+/g, " ")).toContain(
      "Estimate priority and record it without asking",
    );
  });
});
