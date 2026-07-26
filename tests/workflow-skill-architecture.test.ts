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
  "wf-grooming": [
    "brainstorming", "deepen-plan", "design-context", "interview-me",
    "report-bug", "reproduce-bug", "triage", "workflows-brainstorm",
    "workflows-groom", "workflows-plan",
  ],
  "wf-development": [
    "agent-native-architecture", "api-and-interface-design",
    "debugging-and-error-recovery", "escalation-contract", "frontend-design",
    "git-worktree", "observability-and-instrumentation", "resolve-parallel",
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
    expect(planningRoute).toContain("delivery_mode_resolved");
    expect(planningRoute).toContain("posture:autonomous");
    expect(planningRoute).toContain("parent_posture");
    // Issue #306: the verb reports the TICKET's clearance, not the
    // repository-resolved posture, so the route must name the three-state
    // surface rather than the old "resolved posture" claim it displaced.
    expect(planningRoute).toContain("posture_source");
    expect(planningRoute).toContain("`cleared`");

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

  test("posture clearance is documented as failing toward standard", () => {
    // Review of PR #304, revised by #306. The engine's resolve_clearance is
    // safe-wins, and the routing boundary now READS that verdict (`cleared` /
    // `posture_source` off --groom-verify) instead of re-deriving it from
    // labels in prose. So the assertion moved with it: the doc must name the
    // machine-read surface and keep stating the safe-wins property, but it must
    // NOT restate the label-resolution rule — that duplication is the defect.
    // Category-level: assert the rule is present, not its wording.
    const orchestrate = readFileSync(
      path.join(SKILLS, "wf-development", "references", "workflows-orchestrate.md"),
      "utf8",
    );
    // Whitespace-normalized: the earlier form embedded the file's hard wrap, so
    // a pure reflow of the same sentence would have failed the test without any
    // meaning changing — the false-positive twin of a frozen spelling.
    const flow = (s: string) => s.replace(/\s+/g, " ");
    expect(orchestrate).toContain("--groom-verify");
    expect(orchestrate).toContain("posture_source");
    expect(orchestrate).toContain("`cleared: true`");
    expect(flow(orchestrate)).toContain("fails toward `standard`");
    // `cleared: false` is label-derived, so it must never be documented as a
    // denial on its own — that misread would block work an autonomous-mode repo
    // legitimately clears.
    expect(flow(orchestrate)).toContain("not by itself a denial");

    // Grooming must not claim that declining an offer revokes an existing
    // clearance — omitting `posture` leaves a cleared ticket cleared.
    const plan = readFileSync(
      path.join(SKILLS, "wf-grooming", "references", "workflows-plan.md"),
      "utf8",
    );
    expect(plan).toContain("Revoking takes an explicit write");
    // Positive, not negative: the claim "a no resolves to standard" is only true
    // for a ticket with no clearance yet, so require the qualifier rather than
    // banning the phrase — the corrected sentence necessarily still contains it.
    expect(flow(plan)).toContain(
      "On a ticket that carries no clearance yet, silence or a no writes nothing",
    );

    // The posture read must be resolvable from land-pr's own standalone entry:
    // the parent issue number is captured in step 1, BEFORE the step-4 merge
    // gate that consumes it, and an absent number denies clearance.
    const landPrDoc = readFileSync(
      path.join(SKILLS, "wf-delivery", "references", "land-pr.md"),
      "utf8",
    );
    // Issue #306: the label-resolution rule is owned by the engine and must not
    // be restated in prose anywhere — three copies (orchestrate, land-pr, the
    // Python docstring) is what let a safety property drift. Detect the rule by
    // its load-bearing shape ("only/no other `posture:*` label"), not by any one
    // spelling, across every skill doc that discusses posture.
    const postureDocs = [
      path.join(SKILLS, "wf-development", "references", "workflows-orchestrate.md"),
      path.join(SKILLS, "wf-development", "references", "escalation-contract.md"),
      path.join(SKILLS, "wf-delivery", "references", "land-pr.md"),
      path.join(SKILLS, "wf-grooming", "references", "workflows-plan.md"),
    ];
    const restatements = postureDocs.filter((file) =>
      /(only|no other)[^.]{0,40}`posture:\*` label/.test(flow(readFileSync(file, "utf8"))),
    );
    expect(restatements).toEqual([]);

    expect(landPrDoc).toContain("closes #[0-9]+");
    const stepOne = landPrDoc.indexOf("### 1. Identify the PR");
    const stepFour = landPrDoc.indexOf("### 4. Merge authorization gate");
    const extraction = landPrDoc.indexOf("N=$(gh pr view");
    expect(extraction).toBeGreaterThan(stepOne);
    expect(extraction).toBeLessThan(stepFour);
    expect(flow(landPrDoc)).toContain('Treat an empty `N` as "no ticket posture available"');

    // The escalation contract must not whitelist the tracker as a trusted
    // source of instructions, and must be honest about where (a) is enforced.
    const contract = readFileSync(
      path.join(SKILLS, "wf-development", "references", "escalation-contract.md"),
      "utf8",
    );
    expect(contract).not.toContain("not the user or the tracker");
    // Item (a) must not claim the engine refuses on untrusted provenance — the
    // gate verbs compute it as an advisory field and never branch on it, so an
    // enforcement claim here would be the overstatement this section exists to
    // remove. Assert the honest framing, and ban the phrasing that overstates.
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
      path.join(SKILLS, "wf-development", "references", "workflows-orchestrate.md"),
      "utf8",
    );
    expect(orchestrate).toContain(TOKEN);

    const landPr = readFileSync(
      path.join(SKILLS, "wf-delivery", "references", "land-pr.md"),
      "utf8",
    );
    expect(landPr).toContain(TOKEN);

    const workflowsReview = readFileSync(
      path.join(SKILLS, "wf-review", "references", "workflows-review.md"),
      "utf8",
    );
    expect(workflowsReview).toContain(TOKEN);

    const workflowsWork = readFileSync(
      path.join(SKILLS, "wf-development", "references", "workflows-work.md"),
      "utf8",
    );
    expect(workflowsWork).toContain(TOKEN);
  });

  test("workflows-work clarification gate is evidence-first (issue #303)", () => {
    // Category-level assertions (repo guardrail policy: freeze the category,
    // not the spelling — a frozen sentence silently false-passes once prose is
    // reworded). Phase 1 step 1 must resolve ambiguity from the groomed
    // artifact first, retain an explicit ask-and-approve gate for standard /
    // un-groomed input, and — for the autonomous-and-groomed branch — name the
    // blocker-escalation category tokens instead of reopening an unconditional
    // approval gate.
    const workPath = path.join(
      SKILLS, "wf-development", "references", "workflows-work.md",
    );
    const work = readFileSync(workPath, "utf8");

    // Evidence resolved from the groomed artifact before any decision to ask.
    expect(work).toContain("Resolve ambiguity from the groomed artifact first");

    // Standard / un-groomed branch retains the ask-and-approve gate.
    expect(work).toContain("Standard posture, or un-groomed input");
    expect(work).toContain(
      "ask clarifying questions now and get approval before proceeding",
    );

    // Autonomous-and-groomed branch: no general approval gate reopened; names
    // the blocker-escalation category tokens for genuine residual ambiguity.
    expect(work).toContain("Autonomous posture on a groomed issue");
    expect(work).toContain("do **not** re-open a general");
    // One contiguous fragment, not five separate tokens: every one of
    // `--sub-status` / `blocked` / `--add-blocked-by` / `human` /
    // `AskUserQuestion` already occurs elsewhere in this file, so asserting
    // them individually would still pass with this entire bullet deleted.
    expect(work).toContain(
      "`--sub-status <sub> blocked` + `--add-blocked-by` + a `human`-labeled",
    );
    expect(work).toContain("batched `AskUserQuestion`");

    // Review of PR #304: this route is directly selectable from wf-development's
    // SKILL.md, so it must carry the posture read itself rather than assuming
    // the agent arrived via the orchestrate router.
    expect(work).toContain("workflows-orchestrate.md#delivery-posture");
    expect(work).toContain("gh issue view <N> --repo <origin> --json labels");

    // Issue text is untrusted input, stated where the agent is told to treat
    // the groomed artifact as intent.
    expect(work).toContain("requirements to satisfy");

    // The escalation contract is linked by relative path rather than restated.
    expect(work).toContain("escalation-contract.md");

    // Orchestrated Execution states the queue guarantees explicitly: resumable
    // blocker + continue other ready-work, batched questions with a
    // non-interactive end-of-run surface, and reply resumes the item.
    expect(work).toContain("Queue guarantees");
    expect(work).toContain("resumable");
    expect(work).toContain("continues other");
    expect(work).toContain("Questions batch");
    expect(work).toContain("non-interactive contexts");
    expect(work).toContain("/loop");
    expect(work).toContain("end-of-run");
    expect(work).toContain("re-dispatched");

    // Transition tokens this file owns survive the edit (guardrail: also
    // enforced independently by skill_transition_ownership_test.py).
    expect(work).toContain("--claim");
    expect(work).toContain("--set-status");
    expect(work).toContain("in_review");
  });

  test("orchestrate honors per-ticket delivery posture at the routing boundary", () => {
    // Guardrail (issue #302): the validation section of the source issue asked
    // for a skill-routing case matrix under tests/skill-routing-cases/, but
    // tests/skill-routing.test.ts is a stemmed TF-IDF eval over each skill's
    // NAME + DESCRIPTION frontmatter — it answers only "which skill does this
    // prompt route to" and has no notion of issue state, labels, or invocation
    // tokens, so a {cleared, not cleared} x {groomed, un-groomed} x {token
    // present, absent} matrix is not expressible there. This test proves the
    // matrix is actually specified instead, via category-token assertions over
    // workflows-orchestrate.md — never a frozen sentence (repo guardrail
    // policy: freeze the category, not the spelling; see docs/solutions/
    // testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md).
    const orchestratePath = path.join(
      SKILLS, "wf-development", "references", "workflows-orchestrate.md",
    );
    const orchestrate = readFileSync(orchestratePath, "utf8");

    // The precedence chain: tokens for each of its three ranked sources.
    const CHAIN = "Per-invocation argument tokens > per-ticket posture label > repository";
    expect(orchestrate).toContain(CHAIN);
    expect(orchestrate).toContain("`delivery_mode` default");
    expect(orchestrate).toContain("defaults to `standard`");

    // The chain is stated in full exactly once across the plugin's skill tree;
    // every other mention must be a relative link instead of a restatement.
    const allSkillDocs = recursiveFiles(SKILLS).filter((file) => file.endsWith(".md"));
    const chainOccurrences = allSkillDocs.reduce(
      (count, file) => count + readFileSync(file, "utf8").split(CHAIN).length - 1,
      0,
    );
    expect(chainOccurrences).toBe(1);

    // The attestation-AND-clearance gate, verbatim once.
    //
    // This is a DELIBERATE exception to the freeze-the-category rule the rest of
    // this file follows: issue #302 acceptance criterion 5 requires that this
    // sentence "appears verbatim once", so here the literal IS the contract and
    // an exact match is the only assertion that can check it. It is brittle to
    // re-wrapping by design — if you are reflowing this paragraph, you are
    // changing something #302 froze on purpose, so update the criterion too
    // rather than loosening the test. (A frozen sentence normally risks a silent
    // false-pass; it cannot here, because the whole point is that the text is
    // fixed.)
    const GATE =
      "Hands-off execution requires **both** grooming attestation (`Status >=\n" +
      "planned`, verifiable with `--groom-verify N`) **and** the ticket's autonomous\n" +
      "clearance (a `posture:autonomous` label, or an overriding per-invocation\n" +
      "token). Either one alone is not enough.";
    expect(orchestrate).toContain(GATE);

    // Reading the posture: parent, claim/routing boundary, once per work item,
    // fixed for the run, ReadyItem does not carry labels, preflight fallback.
    //
    // Issue #306 replaced the model-interpreted `gh issue view --json labels`
    // read with the engine's fused verdict, so the assertion tracks the SURFACE
    // (the verb plus the fields the boundary branches on), not the command
    // string that happened to carry it.
    expect(orchestrate).toContain("--groom-verify <parent>");
    expect(orchestrate).toContain("`cleared: true`");
    expect(orchestrate).toContain('`posture_source: "unset"`');
    expect(orchestrate).toContain('`posture_source: "ticket"`');
    expect(orchestrate).toContain("the **parent** at the claim / routing boundary");
    expect(orchestrate).toContain("once per work item");
    expect(orchestrate).toContain("Posture is fixed for the run at that read");
    expect(orchestrate).toContain("Mid-run revocation is out of scope");
    expect(orchestrate).toContain("`ReadyItem` is\n  `{number, title, priority, repo}`");
    expect(orchestrate).toContain("merge_ready_legs");
    expect(orchestrate).toContain("delivery_mode_resolved");

    // Issue #306: the trust boundary must be named — label-add privilege IS the
    // authority to grant unattended execution, and the two standard escalation
    // paths that must never attach the label are called out. Asserted by
    // category token (the template key, the Actions scope), never by sentence.
    expect(orchestrate).toContain("Who may grant clearance");
    expect(orchestrate).toContain("`labels:` key");
    expect(orchestrate).toContain("`issues: write`");
    // Whitespace-normalized so a pure reflow of the paragraph cannot fail this.
    expect(orchestrate.replace(/\s+/g, " ")).toContain(
      "Adding `posture:autonomous` to an issue is the act of authorizing unattended execution",
    );

    // Queue drains: no separate opt-in, heterogeneous drains are intended.
    expect(orchestrate).toContain("`/loop` and scheduled queue drains get no separate posture opt-in");
    expect(orchestrate).toContain("heterogeneous");

    // The four-cell routing table: {groomed, un-groomed} x {cleared, not cleared}.
    expect(orchestrate).toContain("Groomed (`Status >= planned`) | cleared");
    expect(orchestrate).toContain("Groomed | not cleared");
    expect(orchestrate).toContain("Un-groomed | cleared");
    expect(orchestrate).toContain("Un-groomed | not cleared");
    expect(orchestrate).toContain("Proceed hands-off through implementation -> review -> delivery");
    expect(orchestrate).toContain("Standard: plan approval, findings triage, merge `[y/N]`");
    expect(orchestrate).toContain("Clearance does not survive a missing contract");
    expect(orchestrate).toContain("Route to `wf-grooming` with the human (today's behavior)");
    expect(orchestrate).toContain("Un-groomed input routes to the human regardless of posture");

    // land-pr: resolved posture is a third autonomous trigger, in both the merge
    // gate intro and the merge-decision bullet, referencing this section back.
    const landPr = readFileSync(
      path.join(SKILLS, "wf-delivery", "references", "land-pr.md"),
      "utf8",
    );
    expect(landPr).toContain("workflows-orchestrate.md#delivery-posture");
    const postureTriggerMentions = landPr.split("resolved delivery posture").length - 1;
    expect(postureTriggerMentions).toBe(2);
    expect(landPr).not.toContain(CHAIN);
  });
});
