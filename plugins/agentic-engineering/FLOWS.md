# Workflow Flows

Visual reference for the plugin's engineering pipeline. Each "flow" below is a slash command; together they form the compounding-engineering loop. Diagrams render natively on GitHub.

## Legend

The same shape language is used in every diagram:

| Shape | Meaning |
|-------|---------|
| `([ rounded ])` | Start / end of a flow |
| `[ rectangle ]` | Automatic step (no user input needed) |
| `{ diamond }` | Automatic decision (the agent decides) |
| `{{ hexagon }}` | **Human checkpoint** — your input / steering |
| `[[ subroutine ]]` | Mandatory gate or a delegated sub-command |

`*` on a node = runs **only when applicable** (e.g. UI changes only).

---

## The big picture

How the individual flows compose into one pipeline, with the artifact each stage leaves behind (these artifacts are what makes the pipeline resumable):

```mermaid
flowchart LR
    idea([feature idea]) --> B["brainstorm"]
    B -->|"docs/brainstorms/*.md<br/><b>brainstormed</b>"| P["plan"]
    P -->|"docs/plans/*-plan.md<br/>+ github_issue<br/><b>planned</b>"| D{"deepen?"}
    D -->|yes| DP["deepen-plan"]
    D -->|no| W
    DP --> W["work"]
    W -->|"PR opened<br/><b>in_progress → in_review</b>"| R["review / land"]
    R --> TB["test-browser*"]
    TB --> FV["feature-video*"]
    FV --> C["compound"]
    R -->|"merge<br/><b>shipped</b>"| C
    C -->|"docs/solutions/*.md<br/><b>compounded</b>"| done([compounded])
```

The **bold** labels are the lifecycle stages stamped on the board's Status field as each artifact lands (see the state machine below). `/workflows:orchestrate` runs this whole chain for you. `/lfg` and `/slfg` run it fully autonomously.

---

## The lifecycle state machine

In `github-project` mode a GitHub Projects v2 board is the source of truth. Every work item is an issue on the board carrying a Status stage; every command reads and moves that stage through one engine (`scripts/lifecycle_board.py`) instead of inferring pipeline position from filenames. This is the canonical picture — the [`lifecycle` skill](skills/lifecycle/SKILL.md) is the prose definition.

Each transition has exactly **one writer** (a command, a built-in automation, or the shared reconciler). Forward stages are strictly ordered except two legal skips (`stub → planned`, `shipped → compounded`). `deployed` and `compounded` are order-independent terminal refinements of `shipped`; `abandoned` is an off-ramp reachable from **any** stage — closing an item as not-planned abandons it even after it shipped (the reconciler honors an explicit not-planned close as a deliberate human act; the `deployed` high-water rule applies to rollbacks, not to not-planned closes).

```mermaid
stateDiagram-v2
    [*] --> stub
    stub --> brainstormed: brainstorm
    stub --> planned: plan (crisp)
    brainstormed --> planned: plan
    planned --> in_progress: work --claim
    in_progress --> in_review: work (PR opens, Closes #N)
    in_review --> shipped: merge → "Item closed" automation

    shipped --> deployed: consumer deploy workflow
    shipped --> compounded: compound
    note right of deployed
        deployed & compounded are order-independent
        refinements of shipped. deployed is a
        high-water mark — rollbacks never regress it.
    end note

    stub --> abandoned: abandoned
    brainstormed --> abandoned
    planned --> abandoned
    in_progress --> abandoned
    in_review --> abandoned
    shipped --> abandoned: not-planned close
    deployed --> abandoned
    compounded --> abandoned

    deployed --> [*]
    compounded --> [*]
    abandoned --> [*]

    note left of shipped
        Reconciler repairs (labeled by rule):
        merged_close_missed: (closed+merged, <shipped) → shipped
        not_planned_close: (closed as not-planned) → abandoned
        pr_closed_unmerged: in_review → in_progress
        pr_reopened: in_progress → in_review
        abandoned_cascade: closes a parent's open sub-issues
        Flag (report-only, never repaired):
        merged_to_non_default_branch → git-flow stall
    end note
```

**Writers per transition:**

| Transition | Writer |
|---|---|
| → `stub` | `/triage`, `/upstream-scan`, humans (create + board-add + `--set-status stub`) |
| → `brainstormed` | `/workflows:brainstorm` (on doc completion) |
| → `planned` | `/workflows:plan` Step 7 (issue + sub-issues + deps + `--set-status planned`) |
| → `in_progress` | `/workflows:work` Phase 1 (`--claim`) |
| → `in_review` | `/workflows:work` Phase 4 (PR opens; issue NOT closed) |
| → `shipped` | Built-in "Item closed" automation (merge automation stamps it) |
| → `deployed` | Consumer repo's deploy workflow (comment-always / Status-best-effort) |
| → `compounded` | `/workflows:compound` (join key present only) |
| → `abandoned` | Humans; reconciler on close-as-not-planned |
| *repairs / cascade* | The shared reconciler (the five labeled repairs; the `abandoned_cascade` on sub-issues) |

The three report-only flags (`merged_to_non_default_branch`, `stale_join_key`, `truncated_ready_work`) emit issue comments + JSON but are never auto-repaired — the repair set stays closed at five.

---

## /workflows:orchestrate — the orchestrator layer

The orchestrator drives every stage automatically. In the default **delegate** mode it delegates implementation to sub-agents, reviews their diffs itself, self-answers the intermediate gates (logging every decision), and stops at exactly one hexagon — the **Final-Review gate** — plus genuine blockers. `--steer` restores the classic cadence where every hexagon below pauses for you.

```mermaid
flowchart TD
    start(["/workflows:orchestrate"]) --> detect["reconcile + read board stage<br/>(legacy artifact fallback)"]
    detect --> B["brainstorm"]
    B --> g1{{"approach selection †"}}
    g1 --> P["plan"]
    P --> gate{{"PLAN-APPROVAL GATE †<br/>(delegate: plan self-review)"}}
    gate -->|deepen| DP["deepen-plan"]
    DP --> gate
    gate -->|proceed| W["work → sub-agents implement,<br/>orchestrator reviews diffs → opens PR"]
    W --> R["review (multi-agent)"]
    R --> p1["auto-fix P1 findings"]
    p1 --> g2{{"findings triage †<br/>(delegate: fix P2, defer P3)"}}
    g2 --> resolve["resolve approved findings"]
    resolve --> TB["test-browser*"]
    TB --> FV["feature-video*"]
    FV --> L["land-pr: drive CI green"]
    L --> g3{{"FINAL-REVIEW GATE ‡<br/>packet + decision log"}}
    g3 --> M["merge"]
    M --> C["compound"]
    C --> done([compounded])

    classDef gate fill:#ffe8cc,stroke:#e8590c,stroke-width:2px;
    class g1,gate,g2,g3 gate
```

† pauses for you in `--steer`/`--careful`; in delegate mode the orchestrator self-answers and logs the decision.
‡ delegate mode's single gate; the `--auto` modifier collapses it (auto-merge once landable, packet becomes the final summary).

**Autonomy dial:** `--careful` > `--steer` > *delegate (default)*; `--auto` is not a fourth mode but a modifier on delegate that toggles only the Final-Review gate. Blockers and material scope changes escalate in **every** mode. In delegate mode, the optional `ralph-wiggum` loop keeps the run moving — but surviving gates still pause it, exactly like `/goal`.

---

## /workflows:brainstorm — decide WHAT to build

```mermaid
flowchart TD
    start([feature idea]) --> clarity{"requirements<br/>already clear?"}
    clarity -->|yes| suggest{{"suggest going straight to plan"}}
    clarity -->|no| research["lightweight repo research<br/>(repo-research-analyst)"]
    research --> dialogue["collaborative dialogue<br/>(AskUserQuestion, one at a time)"]
    dialogue --> approaches["propose 2-3 approaches<br/>with pros / cons"]
    approaches --> pick{{"you pick the approach"}}
    pick --> capture["write brainstorm doc"]
    capture --> open{"open questions?"}
    open -->|yes| resolve{{"resolve each with you"}}
    resolve --> capture
    open -->|no| handoff{{"handoff: proceed to plan?"}}
    handoff --> plan(["/workflows:plan"])

    classDef gate fill:#ffe8cc,stroke:#e8590c,stroke-width:2px;
    class suggest,pick,resolve,handoff gate
```

---

## /workflows:plan — decide HOW to build it

Tracker-issue creation (Step 7) is a hard gate enforced by the `plan-tracker-guard` Stop hook: the plan cannot exit without a `github_issue` join key (or an explicit `issue_tracker: none`). In `github-project` mode Step 7 also creates the sub-issues + dependencies, adds the item to the board, and stamps Status=`planned`.

```mermaid
flowchart TD
    start([feature / brainstorm]) --> bs{"recent brainstorm<br/>matches?"}
    bs -->|yes| usebs["use brainstorm as foundation"]
    bs -->|no| refine["idea refinement<br/>(AskUserQuestion)"]
    usebs --> research["local research (parallel):<br/>repo-research + learnings"]
    refine --> research
    research --> decide{"external research<br/>worth it?"}
    decide -->|"high-risk / uncertain"| ext["best-practices +<br/>framework-docs researchers"]
    decide -->|"strong local context"| consolidate["consolidate findings"]
    ext --> consolidate
    consolidate --> specflow["spec-flow-analyzer"]
    specflow --> detail{"detail level<br/>MINIMAL / MORE / A LOT"}
    detail --> writefile["write plan file"]
    writefile --> tracker[["Step 7: issue + sub-issues + board add,<br/>Status=planned (MANDATORY GATE)"]]
    tracker --> guard{"github_issue recorded?"}
    guard -->|no| tracker
    guard -->|yes| opts{{"post-generation options"}}

    classDef gate fill:#ffe8cc,stroke:#e8590c,stroke-width:2px;
    class opts gate
```

---

## /deepen-plan — enrich the plan with parallel research

Fans out one sub-agent per matched skill, per relevant learning, per plan section, and per discovered review agent — then merges everything back into the plan in place.

```mermaid
flowchart TD
    start([plan file]) --> parse["parse plan into sections"]
    parse --> fan["fan out in parallel"]
    fan --> skills["matched-skill sub-agents"]
    fan --> learnings["learnings sub-agents<br/>(docs/solutions)"]
    fan --> sections["per-section research<br/>(Explore + Context7 + WebSearch)"]
    fan --> reviewers["ALL review agents"]
    skills --> synth["synthesize + dedupe + prioritize"]
    learnings --> synth
    sections --> synth
    reviewers --> synth
    synth --> enhance["enhance each section in place"]
    enhance --> opts{{"post-enhancement options"}}

    classDef gate fill:#ffe8cc,stroke:#e8590c,stroke-width:2px;
    class opts gate
```

---

## /workflows:work — execute the plan and ship a PR

Mode-aware (`github-project` / `github` / `none`) and supports three execution styles: **inline** (default), **orchestrated** (one sub-agent per sub-issue), and **swarm** (parallel teammates). In `github-project` mode Phase 1 claims the item via `--claim` (Status=`in_progress`); Phase 4 opens the PR with `Closes #N` and sets Status=`in_review` — the issue is **not** closed at PR creation. The merge automation stamps `shipped`.

```mermaid
flowchart TD
    start([plan / spec]) --> readplan["read plan completely"]
    readplan --> clar{"anything ambiguous?"}
    clar -->|yes| ask{{"clarify with you"}}
    ask --> preflight
    clar -->|no| preflight["repo preflight script:<br/>resolve mode"]
    preflight --> claim["lifecycle_board.py --claim<br/>(Status=in_progress)"]
    claim --> branch["branch / worktree setup"]
    branch --> tasks["create task list<br/>(sub-issues or TodoWrite)"]
    tasks --> loop{"tasks remain?"}
    loop -->|yes| impl["implement → test →<br/>system-wide check → commit"]
    impl --> loop
    loop -->|no| quality["quality checks:<br/>tests + lint + integration boundaries"]
    quality --> ship["commit + capture screenshots*"]
    ship --> pr[["open PR (Closes #N),<br/>Status=in_review — issue NOT closed"]]
    pr --> done([PR open])

    classDef gate fill:#ffe8cc,stroke:#e8590c,stroke-width:2px;
    class ask gate
```

---

## /workflows:review — multi-agent code review

Runs configured review agents in parallel (plus conditional migration agents), synthesizes findings into P1/P2/P3, and records them as `todos/*.md` file-todos. P1 findings block merge.

```mermaid
flowchart TD
    start([PR / branch]) --> setup["checkout target<br/>(worktree if needed)"]
    setup --> agents["run review agents in parallel"]
    agents --> core["security, performance, architecture,<br/>kieran-*, agent-native, ..."]
    agents --> cond["conditional: migration agents*<br/>(if schema / data changes)"]
    core --> simp["code-simplicity-reviewer"]
    cond --> simp
    simp --> synth["synthesize + dedupe<br/>+ assign P1 / P2 / P3"]
    synth --> track["create findings<br/>(todos/*.md)"]
    track --> report["summary report"]
    report --> e2e{"offer E2E testing"}
    e2e --> done([findings tracked])
```

---

## /workflows:compound — capture the solution

Phase-1 sub-agents return **text only**; only the orchestrator (Phase 2) writes a single file. Knowledge compounds: the next occurrence of this problem is a lookup, not a re-investigation.

```mermaid
flowchart TD
    start([solved problem]) --> phase1["Phase 1: parallel research<br/>(sub-agents return TEXT, write nothing)"]
    phase1 --> ctx["context analyzer"]
    phase1 --> sol["solution extractor"]
    phase1 --> rel["related-docs finder"]
    phase1 --> prev["prevention strategist"]
    phase1 --> cat["category classifier"]
    ctx --> assemble["Phase 2: orchestrator assembles<br/>+ writes ONE file"]
    sol --> assemble
    rel --> assemble
    prev --> assemble
    cat --> assemble
    assemble --> file["docs/solutions/&lt;category&gt;/&lt;file&gt;.md"]
    file --> enh["Phase 3: optional specialist review*"]
    enh --> done([knowledge captured])
```

---

## /lfg and /slfg — fully autonomous (no human in the loop)

`/lfg` runs the pipeline end to end without stopping. `/slfg` is the same, but runs work in swarm mode and review + test-browser in parallel.

```mermaid
flowchart LR
    ralph["ralph-loop*"] --> plan["plan"] --> deepen["deepen-plan"] --> work["work"] --> review["review"] --> resolve["resolve_todo_parallel"] --> tb["test-browser"] --> fv["feature-video"] --> done(["&lt;promise&gt;DONE&lt;/promise&gt;"])
```

```mermaid
flowchart TD
    plan["plan"] --> deepen["deepen-plan"] --> work["work (swarm mode)"]
    work --> review["review (parallel)"]
    work --> tb["test-browser (parallel)"]
    review --> resolve["resolve_todo_parallel"]
    tb --> resolve
    resolve --> fv["feature-video"] --> done([DONE])
```

`/workflows:orchestrate` sits between these two extremes: it runs the same operations as `/lfg`, but pauses at the human checkpoints shown in the orchestrate diagram above.
