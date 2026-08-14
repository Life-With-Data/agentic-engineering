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

## Routing and delegation

`wf-orchestrate` is the default end-to-end entry point. It resolves current
state and uses only the specialist workflows the request and risk require,
always routing through `wf-review` between development and delivery. Stage
skills can also be invoked directly, and small stage transitions may run inline
instead of creating handoffs.

`wf-auto` is the explicit unattended entry point. It selects ready work when
needed, suppresses routine check-ins, and delegates routing to
`wf-orchestrate`. It is the only route that may explicitly force the
`ready_for_work` approval stamp after grooming. It does not weaken repository
checks or grant authority for credentials, destructive scope expansion,
force-pushes, or admin overrides.

Sub-agents are optional. Use them for independent parallel units or a valuable
independent risk check; keep small or tightly coupled changes inline. The
coordinating agent retains shared tracker, board, and PR writes and verifies
delegated results.

## Standard workflow set

Each router states its own required capabilities in its `Requires` line.
Routes may require more capabilities. Production diagnosis requires
`observability`; deployments require `infrastructure-operations` and
`security-and-access`.

For bugs, reproduce when practical, then localize, fix, and verify the affected
behavior. `wf-review` always follows before delivery, scaling its depth to risk;
use a separate testing pass when risk or missing evidence justifies it. Do not
require four handoffs for every bug.

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
