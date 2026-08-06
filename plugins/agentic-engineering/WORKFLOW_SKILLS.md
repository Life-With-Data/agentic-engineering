# Workflow skill architecture

The distributable plugin exposes exactly nine workflow-policy skills. Every
public skill uses the `wf-` prefix. Repository operational guidance keeps the
consumer repository's existing names and structure; the plugin requires a
capability map, not wrapper skills.

## Orthogonal layers

| Layer | Location | Owns | Must not own |
|---|---|---|---|
| Workflow policy | Plugin `skills/wf-*/SKILL.md` | Stages, gates, routing, completion | Repository commands, credentials, infrastructure mechanics |
| Repository contract | Root `AGENTS.md` | Fixed capability-to-asset mapping | Workflow procedures or duplicated operational guidance |
| Repository operations | Repository skills or docs | Commands, environments, access procedures, observable evidence | Workflow stages or plugin completion criteria |

Every `wf-*` router labels itself `Layer: Workflow policy`, lists its required
capabilities, and states what it excludes. If an agent opens repository guidance
first, that guidance supplies mechanics only and points back to workflow policy
for sequencing. If it opens workflow policy first, capability validation routes
it to the repository mechanics it needs.

## Vertical delegation

Delegation is vertical, never horizontal. `wf-orchestrate` sits at the top:
it is the default entry point for any work item, resolves the item's current
lifecycle stage from tracker evidence, reads delivery posture, and dispatches
the owning stage skill at each boundary. Stage skills are workers: each owns
exactly its stage, applies its own gates, reports completion evidence, and
returns control to the orchestrator. A stage skill never routes laterally to
a sibling stage, never decides what runs next in the pipeline, and never
inlines another stage's procedure.

`wf-auto` sits above the orchestrator without adding a layer: it selects the
ticket when the caller names none, suppresses every optional check-in for the
run, and dispatches `wf-orchestrate`. It owns no stage and no gate.

Two consequences:

- **Invoke `wf-orchestrate` by default.** A request that spans stages — "fix
  this bug", "build this feature", "drain the ready queue" — enters through
  the orchestrator. Invoke a stage skill directly only for a genuinely
  single-stage request, and it then reports its own completion instead of
  continuing the pipeline.
- **Cross-cutting policy lives at the top.** The escalation contract,
  sub-agent delegation policy, and delivery-posture resolution are
  `wf-orchestrate` references. Stage skills link up to them; they never
  restate them.

Within any stage, the session's default agent is the **orchestrator and
validator**, not the worker: it dispatches focused sub-agents for stage work,
verifies each result independently, sets each sub-agent's model explicitly at
dispatch, and owns every tracker or board write. Sub-agents never mutate
shared tracker, board, or PR state. The canonical policy is
`wf-orchestrate`'s sub-agent delegation reference; each router carries only
its stage-specific posture. Hosts without a sub-agent mechanism run the same
sequences inline — delegation is an execution model, never a gate.

## Standard workflow set

Each router states its own required capabilities in its `Requires` line.
Routes may require more capabilities. Production diagnosis requires
`observability`; deployments require `infrastructure-operations` and
`security-and-access`.

Bug handling crosses stages under the orchestrator instead of becoming a
separate top-level skill:

1. `wf-grooming` owns report completeness and verified reproduction.
2. `wf-development` owns localization, root cause, and the fix.
3. `wf-testing` owns regression protection and the original reproduction rerun.
4. `wf-review` evaluates the fix and its risks.

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
`## Agentic Engineering Repository Contract` in root `AGENTS.md`. Every router
bundles its own `scripts/repository-context.py` so a selected skills-only
install remains executable without plugin-level files. The key names, value
grammar, and inventory-first interview live in the
[`wf-setup` repository-context contract](skills/wf-setup/references/repository-context-contract.md).

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
