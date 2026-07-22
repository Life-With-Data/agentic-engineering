# Workflow skill architecture

The distributable plugin exposes exactly seven workflow-policy skills. Every
public skill uses the `wf-` prefix. Repository operational guidance keeps the
consumer repository's existing names and structure; the plugin requires a
capability map, not wrapper skills.

## Orthogonal layers

| Layer | Location | Owns | Must not own |
|---|---|---|---|
| Workflow policy | Plugin `skills/wf-*/SKILL.md` | Stages, gates, handoffs, completion | Repository commands, credentials, infrastructure mechanics |
| Repository contract | Root `AGENTS.md` | Fixed capability-to-asset mapping | Workflow procedures or duplicated operational guidance |
| Repository operations | Repository skills or docs | Commands, environments, access procedures, observable evidence | Workflow stages or plugin completion criteria |

Every `wf-*` router labels itself `Layer: Workflow policy`, lists its required
capabilities, and states what it excludes. If an agent opens repository guidance
first, that guidance supplies mechanics only and points back to workflow policy
for sequencing. If it opens workflow policy first, capability validation routes
it to the repository mechanics it needs.

## Standard workflow set

| Skill | Use it for | Base repository capabilities |
|---|---|---|
| `wf-grooming` | Discovery, brainstorming, triage, bug reproduction, grooming, planning | `repository-overview`, `documentation`; bugs also require `development-environment` and `bug-reproduction` |
| `wf-development` | Implementation, diagnosis, refactoring, APIs, frontend and agent systems | `repository-overview`, `development-environment`, `test-execution` |
| `wf-testing` | Test strategy, TDD, interface checks and verification | `development-environment`, `test-execution` |
| `wf-review` | Code, architecture, security and PR review | `repository-overview`, `test-execution` |
| `wf-delivery` | CI, PRs, merge, release and deployment handoff | `test-execution`, `delivery` |
| `wf-documentation` | Documentation creation, review, compounding and publication | `repository-overview`, `documentation` |
| `wf-setup` | Capability-contract adoption, lifecycle, configuration and hooks | None before bootstrap; a complete contract is mandatory before setup finishes |

Routes may require more capabilities. Production diagnosis requires
`observability`; deployments require `infrastructure-operations` and
`security-and-access`.

Bug handling deliberately crosses workflows instead of becoming a separate
top-level skill:

1. `wf-grooming` owns report completeness and verified reproduction.
2. `wf-development` owns localization, root cause, and the fix.
3. `wf-testing` owns regression protection and the original reproduction rerun.
4. `wf-review` evaluates the fix and its risks.

## Delegation model

Across every workflow, the session's default agent is the **orchestrator and
validator**, not the worker. It decomposes the task, dispatches focused
sub-agents for stage work (research, implementation units, test authoring,
review lenses, CI diagnosis, documentation drafts), verifies each result
independently, and owns every tracker or board write. Sub-agents never mutate
shared tracker, board, or PR state.

The orchestrator also selects each sub-agent's model at dispatch time based on
that unit's complexity — economy tiers for mechanical work with deterministic
exit checks, standard tiers for well-scoped work against clear criteria, and
the strongest available tier for ambiguous or high-blast-radius work — while
keeping the session's own model for verification and triage. The canonical
policy lives in `wf-development`'s sub-agent delegation reference; each router
carries the stage-specific posture. Hosts without a sub-agent mechanism run
the same sequences inline — delegation is an execution model, never a gate.

## Granular capability references

Condensing skills does not remove precision. Express a granular need as four
separate fields instead of reviving a flat skill name:

1. **Workflow owner** — one discoverable `wf-*` skill.
2. **Route** — a plain-language branch selected inside that skill, not another
   discoverable skill.
3. **Repository capability** — one or more fixed contract keys whose mapped
   assets define local mechanics.
4. **Runtime requirement** — a semantic description of the tool behavior
   needed for this task. Resolve the concrete tool from repository guidance and
   the host's actually available capability metadata.

For example, do not tell an agent to load an `agent-browser` skill. Use:

```text
Workflow owner: wf-testing
Route: browser verification
Repository capabilities: development-environment, test-execution
Runtime requirement: interactive browser navigation, element inspection,
screenshots, and console/network evidence
```

For a UI bug, the workflow owner is `wf-grooming`, the route is bug
reproduction, and `bug-reproduction` joins `development-environment` as the
repository capability. The mapped assets decide whether the concrete mechanism
is a CLI, MCP tool, device harness, manual procedure, or another installed
skill. If neither repository guidance nor host metadata supplies the required
mechanism, report a missing-capability blocker and route to `wf-setup`; never
guess a historical name or silently substitute weaker evidence.

## Fixed repository capability set

Every adopting repository declares `contract-version: 2` and all ten keys under
`## Agentic Engineering Repository Contract` in root `AGENTS.md`:

1. `repository-overview`
2. `development-environment`
3. `test-execution`
4. `bug-reproduction`
5. `observability`
6. `data-operations`
7. `infrastructure-operations`
8. `delivery`
9. `security-and-access`
10. `documentation`

A key maps to one or more ordered, comma-separated repository-relative Markdown
links or to `not-applicable — <concrete reason>`. Omission is invalid. The first
link is primary; later links are supporting context loaded progressively. One
asset may serve several capabilities. Assets need no prefix, plugin metadata,
or one-to-one wrapper.

Every router bundles its own `scripts/repository-context.py` so a selected
skills-only install remains executable without plugin-level files. Other
portable executables are likewise bundled into each consuming skill. The
complete contract format and inventory-first interview live in `wf-setup`.

## Progressive disclosure layout

Each public skill has one discoverable entry point:

```text
skills/wf-<domain>/
├── SKILL.md
├── references/*.md
├── scripts/*       # every executable dependency used by this workflow
└── assets/*        # only when the workflow owns an output artifact
```

Resource directories are flat. References are ordinary Markdown without skill
frontmatter and are opened only through their router. A reference must not
install repository tooling, invent a repository layout, or prescribe a
consumer-owned skill. Framework, language, vendor, and infrastructure mechanics
belong in mapped repository assets or a separately installed capability.

## Migration map

Former standalone skills retained as internal references:

- `wf-grooming`: `brainstorming`, `deepen-plan`, `interview-me`, `report-bug`,
  `reproduce-bug`, `triage`, `workflows-brainstorm`, `workflows-groom`,
  `workflows-plan`
- `wf-development`: `agent-native-architecture`, `api-and-interface-design`,
  `debugging-and-error-recovery`, `frontend-design`, `git-worktree`,
  `observability-and-instrumentation`, `resolve-parallel`,
  `workflows-orchestrate`, `workflows-work`
- `wf-testing`: `test-browser`, `test-driven-development`,
  `test-strategy-reviewer`, `verification-loop`
- `wf-review`: `agent-native-audit`, `doubt-driven-development`,
  `resolve-pr-parallel`, `security-and-hardening`, `workflows-review`
- `wf-delivery`: `changelog`, `ci-resolve-workflow-issues`, `land-pr`,
  `workflows-merge`
- `wf-documentation`: `compound-docs`, `deploy-docs`, `document-review`,
  `land-docs`, `reflect-for-skill-updates`, `workflows-compound`
- `wf-setup`: `config-flags`, `install-hooks`, `lifecycle`,
  `lifecycle-doctor`, `setup`

Plugin-maintenance procedures are repository-local to this repository. They are
not a consumer workflow and therefore are not public plugin skills.

## Adoption sequence

1. Run `wf-setup` to inspect or bootstrap the repository contract.
2. Inventory existing instructions, docs, skills, scripts, CI, and runbooks.
3. Draft direct mappings before asking questions.
4. Interview only for gaps, ambiguity, access, safety, and proposed
   `not-applicable` entries.
5. Create new guidance only when repository knowledge is genuinely missing.
6. Validate the complete contract before setup finishes.
7. Invoke only the owning `wf-*` skill; let its router choose internal
   references and repository assets.
