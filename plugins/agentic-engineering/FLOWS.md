# Workflow flows

Visual reference for the seven public `wf-*` skills and their repository-context handoffs. The detailed procedures shown in parentheses are internal references selected by a router; they are not independently invocable skills.

## The two orthogonal layers

```mermaid
flowchart LR
    request([Engineering request]) --> WF["wf-* workflow policy"]
    WF -->|"required capability names"| C["Root AGENTS.md contract"]
    C -->|"ordered repo-relative pointers"| R["repository operational assets"]
    R -->|"commands, access, and evidence"| WF
    WF --> result([Gated workflow result])
```

- `wf-*` decides **what must happen, in what order, and what counts as complete**.
- Root `AGENTS.md` maps each fixed capability name to one or more repository-owned assets in primary-first reading order.
- Repository-owned guidance decides **how this repository performs the operation**. Its skill names are unconstrained.

Missing or malformed repository context stops every ordinary workflow. `wf-setup` may continue only to repair that context. See [WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md) for the complete contract.

## Public workflow map

```mermaid
flowchart LR
    G["wf-grooming"] --> D["wf-development"]
    D --> T["wf-testing"]
    T --> R["wf-review"]
    R -->|"fix required"| D
    R -->|"ready"| L["wf-delivery"]
    L --> K["wf-documentation"]
    K --> done([Complete])
    S["wf-setup"] -. "adopts and configures" .-> G
```

`wf-development` can coordinate the complete chain for a prepared work item. Ownership does not collapse during orchestration: each downstream router still owns its own gates and repository-capability requirements.

## Grooming and implementation split

```mermaid
flowchart TD
    request([Idea, request, bug report, or issue]) --> G["wf-grooming"]
    G --> intent["confirm intent and scope<br/>(interview / brainstorm route)"]
    intent --> plan["produce acceptance criteria,<br/>validation, plan, and decomposition"]
    plan --> ready([Ready for development])
    ready --> D["wf-development --implement"]
    D --> T["wf-testing"]
    T --> R["wf-review"]
    R --> L["wf-delivery"]
    L --> K["wf-documentation"]
```

The hard boundary is deliberate: `wf-grooming` never claims work or edits product code. `wf-development --implement` refuses to invent missing grooming context and routes back to `wf-grooming`.

## Bug flow

```mermaid
flowchart TD
    report([Unexpected behavior]) --> G["wf-grooming"]
    G --> contract{"bug-reproduction capability valid?"}
    contract -->|no| stop([Stop with contract errors])
    contract -->|yes| evidence["record expected, actual,<br/>environment, and evidence"]
    evidence --> reproduce["reproduce using repo guidance"]
    reproduce --> groom{"report complete and work item ready?"}
    groom -->|no| G
    groom -->|yes| D["wf-development"]
    D --> root["localize, establish root cause,<br/>and implement the fix"]
    root --> T["wf-testing: regression + original reproduction"]
    T --> R["wf-review"]
```

A failed reproduction blocks grooming; it is evidence to report, not permission to plan a speculative fix. Production or integration failures additionally require the `observability` capability.

## Delivery flow

```mermaid
flowchart TD
    implemented([Implemented change]) --> T["wf-testing"]
    T --> R["wf-review"]
    R --> ready{"ready?"}
    ready -->|no| D["wf-development"]
    D --> T
    ready -->|yes| L["wf-delivery"]
    L --> ci["repair CI and resolve threads"]
    ci --> merge{"merge gates pass?"}
    merge -->|no| ci
    merge -->|yes| shipped([Shipped])
    shipped --> deploy["deployment handoff*"]
    shipped --> K["wf-documentation"]
```

`*` Deployment requires `infrastructure-operations` and `security-and-access` in addition to the base `delivery` capability.

## Lifecycle state machine

In `github-project` mode, workflow routes write a closed set of lifecycle transitions through `scripts/lifecycle_board.py`.

```mermaid
stateDiagram-v2
    [*] --> stub
    stub --> brainstormed: wf-grooming brainstorm route
    stub --> planned: wf-grooming plan route
    brainstormed --> planned: wf-grooming plan route
    planned --> in_progress: wf-development claim
    in_progress --> in_review: wf-development opens PR
    in_review --> shipped: merge automation
    shipped --> deployed: repository delivery automation
    shipped --> compounded: wf-documentation compound route

    stub --> abandoned
    brainstormed --> abandoned
    planned --> abandoned
    in_progress --> abandoned
    in_review --> abandoned
    shipped --> abandoned
    deployed --> abandoned
    compounded --> abandoned
```

`deployed` and `compounded` are order-independent refinements of `shipped`. `abandoned` is the explicit off-ramp. The lifecycle reference under `wf-setup` defines entry gates, writer contracts, claims, and the closed repair set.

## Setup flow

```mermaid
flowchart TD
    start(["wf-setup"]) --> validate["run repository contract validator"]
    validate --> valid{"contract valid?"}
    valid -->|no| inventory["inventory existing instructions,<br/>docs, skills, CI, and runbooks"]
    inventory --> draft["draft reusable, ordered mappings"]
    draft --> interview["interview only for gaps,<br/>ambiguity, access, and safety"]
    interview --> validate
    valid -->|yes| configure["configure plugin, lifecycle, and hooks"]
    configure --> doctor["run readiness diagnostics"]
    doctor --> done([Setup complete])
```

`wf-setup` is the only router allowed to continue temporarily after contract validation fails, and only to construct, migrate, or repair the contract. It maps suitable existing assets directly, never creates wrappers merely for naming or metadata, never guesses operational guidance, and cannot finish until strict validation succeeds.

## Progressive disclosure

Each router follows the same sequence:

1. Validate the complete repository contract.
2. Require the capabilities needed by the selected route.
3. Read each capability's primary target, then supporting targets only as needed.
4. Load only the internal procedure needed for the current stage.
5. Return to the router for its handoff and completion gate.

This keeps workflow policy stable across repositories while allowing every repository to supply its own commands, infrastructure, access procedures, and evidence sources.
