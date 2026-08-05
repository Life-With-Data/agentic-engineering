# Agent-Native Architecture Audit

Review the codebase against the agent-native architecture principles below,
launching one parallel sub-agent per principle and producing a scored report.

## Audit Dimensions

Each dimension lists what the auditing sub-agent enumerates and checks.

1. **Action Parity** — "Whatever the user can do, the agent can do."
   Enumerate ALL user actions in the frontend (API calls, button clicks, form
   submissions; search API service files, fetch calls, form handlers, routes,
   components). Map each to a corresponding agent tool. Score: agent can do X
   of Y user actions.

2. **Tools as Primitives** — "Tools provide capability, not behavior."
   Read ALL agent tool files. Classify each as PRIMITIVE (good: read, write,
   store, list — capability without business logic) or WORKFLOW (bad: encodes
   business logic, makes decisions, orchestrates steps). Score: X of Y tools
   are primitives; list workflow tools that should be primitives.

3. **Context Injection** — "System prompt includes dynamic context about app
   state." Find context-injection code and read agent prompts. Compare what
   IS injected against what SHOULD be: available resources (files, drafts,
   documents), user preferences/settings, recent activity, listed
   capabilities, session history, workspace state. Score injected vs. needed.

4. **Shared Workspace** — "Agent and user work in the same data space."
   Identify all data stores/tables/models. Check whether agents read/write
   the SAME stores as users; flag the sandbox-isolation anti-pattern (agent
   has a separate data space). Score shared vs. isolated stores.

5. **CRUD Completeness** — "Every entity has full CRUD." Identify all
   entities/models. For each, check agent tools exist for Create, Read,
   Update, Delete. Score per entity and overall; list missing operations.

6. **UI Integration** — "Agent actions immediately reflected in UI." Check
   how agent writes propagate to the frontend: streaming (SSE, WebSocket),
   polling, shared state/services, event buses, file watching. Flag the
   "silent actions" anti-pattern (agent changes state, UI does not update).

7. **Capability Discovery** — "Users can discover what the agent can do."
   Check the 7 mechanisms: onboarding flow showing capabilities, help
   documentation, capability hints in UI, agent self-describing in responses,
   suggested prompts/actions, empty-state guidance, slash commands
   (/help, /tools). Score X of 7.

8. **Prompt-Native Features** — "Features are prompts defining outcomes, not
   code." Read all agent prompts. Classify each feature as defined in PROMPT
   (good: outcome in natural language) or CODE (bad: hardcoded business
   logic). Check whether behavior changes need a prompt edit or a code
   change. Score prompt-defined vs. code-defined; list code-defined features.

## Workflow

### Step 1: Launch parallel sub-agents

Launch one sub-agent per dimension using the Task tool with
`subagent_type: Explore`, giving it the dimension's principle and checks
above plus this per-dimension report template:

```markdown
## [Dimension] Audit
### Findings
| Instance | Location | Compliant? | Notes |
### Score: X/Y (percentage%)
### Gaps (missing tools, anti-patterns, isolated data, etc.)
### Recommendations
```

Every score is a specific "X out of Y (percentage%)"; every gap names a file
or component.

### Step 2: Compile the summary report

```markdown
## Agent-Native Architecture Review: [Project Name]

### Score Summary
| Dimension | Score | Percentage |
|-----------|-------|------------|
(one row per dimension)

**Overall Agent-Native Score: X%**

### Recommendations by Impact
| Priority | Action | Dimension | Effort |
|----------|--------|-----------|--------|
```

## Success Criteria

- [ ] All sub-agents complete their audits
- [ ] Each dimension has a specific numeric score (X/Y format)
- [ ] The summary table covers every dimension
- [ ] Recommendations are prioritized by impact and reference specific gaps

## Optional: Single Dimension Audit

If $ARGUMENTS names a single dimension, run only that sub-agent and report
its detailed findings. Valid arguments:

- `action parity` or `1`
- `tools` or `primitives` or `2`
- `context` or `injection` or `3`
- `shared` or `workspace` or `4`
- `crud` or `5`
- `ui` or `integration` or `6`
- `discovery` or `7`
- `prompt` or `features` or `8`
