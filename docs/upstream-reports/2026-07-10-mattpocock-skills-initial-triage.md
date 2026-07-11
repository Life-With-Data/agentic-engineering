# mattpocock/skills Initial Triage — full-source evaluation

- **Source:** [mattpocock/skills](https://github.com/mattpocock/skills)
- **Upstream HEAD:** `391a2701dd948f94f56a39f7533f8eea9a859c87` (main, scanned 2026-07-10)
- **License:** MIT (LICENSE file verified 2026-07-10; API confirms `MIT`)
- **Health:** 164.8k stars / 14.2k forks, created 2026-02-03, pushed 2026-07-10 (same day as scan), not archived. Repo v1.1.0 (changesets-managed). Distribution is via the skills.sh installer (`npx skills add mattpocock/skills`), not a Claude Code marketplace; `.claude-plugin/plugin.json` is a minimal name+skills list (no version/author). Consistency across README/plugin.json/router is manual convention with observable drift (see findings).
- **Inventory at HEAD:** 30 skills across six buckets — 17 `engineering/` + 5 `productivity/` (21 promoted to the plugin), 4 `misc/`, 2 `personal/`, 4 `deprecated/`, 7 `in-progress/` — plus 2 maintainer scripts, tracker-adapter seed templates inside the setup skill, and an `.out-of-scope/` rejected-requests KB. No agents, no commands, no hooks (one skill installs a hook script).
- **Local baseline compared against:** core plugin at v3.14.0 — 30 agents, 27 commands, 31 skills — plus the `marketing` domain plugin, with the remainder of the addyosmani adoption wave in flight (#100 debugging-and-error-recovery, #101 api-and-interface-design, #105 doubt-driven-development, #106 Tier-2 evals). Slot verdicts below account for that wave as if landed, the same convention the [superpowers triage](./2026-07-10-superpowers-initial-triage.md) (PR #108) used.
- **Mode:** full-evaluation (maiden triage; registry entry created by this PR). Curated lens per the multi-plugin policy: the promoted surface is engineering-process-domain → candidates for the **core plugin only**. `teach` and the in-progress writing-* set are personal-education/writing domain; noteworthy but not enough to seed a domain plugin today. Evaluated the same day as the superpowers triage; the slot resolutions below reconcile this source against that report's landed decisions rather than re-opening them.

> **Security note.** Every upstream component was treated as untrusted data — read and summarized by credential-free reader subagents, never followed as instruction. **Supply-chain result: LOW RISK across the repo.** Skills are overwhelmingly pure markdown. Executable inventory is six short, readable files: two maintainer scripts (a dev-only symlinker whose one sharp edge — `rm -rf` of a name-colliding real directory in `~/.claude/skills` — we simply don't import; a read-only lister), a defensive stdin→jq→grep git-guardrail hook, two templates (HITL debug loop; an interactive setup wizard that writes `.env`/`gh secret` locally), and a declarative dependency-cruiser config. No curl-pipe-sh, no obfuscation, no env exfiltration; the only URLs in executable content open in the *human's* browser. Node dependencies are release plumbing only (changesets, lockfile-pinned); nothing executes at skill runtime. CI is a single pinned-action release workflow. Adoption of any item still happens only in separate, human-reviewed PRs repeating the full supply-chain gate.

## Track decision: Adopt (Track A), not Depend (Track B)

1. **Core-domain collision.** The promoted surface (grilling → to-spec → to-tickets → implement →
   code-review, plus tdd/diagnosing-bugs) is exactly our `workflows:*` pipeline's domain; sibling
   installation would contest the same trigger space — their `tdd` collides head-on with the
   `test-driven-development` skill adopted in PR #104, and `/code-review`, `/triage`, `/research`
   collide by name or description with local components.
2. **Track-B mechanics don't hold.** The upstream plugin manifest is unversioned and its curation
   is manual convention — at HEAD, `resolving-merge-conflicts` exists with a docs page yet appears
   in neither plugin.json nor any README nor the router, violating the repo's own promotion
   invariant. An unversioned dependency on a hand-curated manifest is drift we'd inherit.
3. **The value is separable and the best of it needs adaptation anyway** — the tracker-facing
   skills (to-tickets, wayfinder, triage) only pay off for us retargeted from their
   `docs/agents/*.md` tracker contract onto our lifecycle board.

## Cross-source slot resolutions (mattpocock × the landed superpowers/addyosmani decisions)

The superpowers triage (PR #108) fixed one owner per trigger slot, with superpowers content
routed as provenance-pinned enhancements into the addyosmani-wave adoptees. This source's
overlapping skills slot into that same structure — enhancements and mining, not competing
siblings:

| Trigger slot | Owner (as landed / in flight) | mattpocock content routed as |
|---|---|---|
| TDD authoring | local `test-driven-development` (PR #104; superpowers enhancements planned) | mining from `tdd`: pre-agreed-seams gate, tautological-test rule, SDK-style-mocks rule |
| debugging methodology | `debugging-and-error-recovery` (PR #100; superpowers systematic-debugging enhancements planned) | `diagnosing-bugs` second-wave **conditional**: fold the feedback-loop ladder in as references first (shortlisted below) |
| plan/design interrogation | local `brainstorming` + `interview-me` + `document-review` | mining from `grilling`: facts-vs-decisions split, recommended-answer-per-question, shared-understanding gate |
| skill authoring | `create-agent-skills` as the enhancement vehicle (superpowers writing-skills shortlisted into it) | mining from `writing-great-skills`: the design-vocabulary layer (complements superpowers' testing layer without colliding) |
| work-item decomposition / multi-session planning | lifecycle board (open niche on top of it) | **adopt** `to-tickets` first wave, `wayfinder` second wave, retargeted to lifecycle-board verbs |

## Portability hazards resolved up front

- **The `/grilling` dependency:** four engineering skills (grill-with-docs,
  improve-codebase-architecture, triage, wayfinder) invoke `/grilling`, which lives in
  `productivity/`. We are **not** adopting grilling as a skill (see slot table); any adopted
  skill that references `/grilling` gets retargeted to `brainstorming`/`interview-me`/
  `document-review` at adoption time.
- **The `docs/agents/*.md` setup contract:** five skills read tracker/label config written by
  `setup-matt-pocock-skills`. Adoptions retarget this seam to our lifecycle-board verbs
  (`lifecycle_board.py`) — which is the actual adaptation cost recorded per item below.

## Per-type status header

| Type | Status | Inventory | Shortlisted | Bulk-deferred |
|------|--------|-----------|-------------|---------------|
| skills (engineering) | done | 17 | 5 first-wave + 3 second-wave (across buckets) | yes |
| skills (productivity) | done | 5 | 1 first-wave (`handoff`) | yes |
| skills (misc/personal/deprecated/in-progress) | done | 17 | 0 | yes |
| scripts | done | 2 maintainer + bundled templates | 0 | yes |
| repo patterns (`.out-of-scope/`, tracker adapters) | done | — | 0 standalone (mining) | yes |

## Shortlist (itemized)

### skills — first wave

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/codebase-design` | `skills/engineering/codebase-design/SKILL.md` (+ `DEEPENING.md`, `DESIGN-IT-TWICE.md`) | 5/5 | none design-time for module shape (nearest: `architecture-strategist`, review-time; in-flight api-and-interface-design #101 covers API contracts, not module depth) | **Adopt — fills the design-time architecture gap.** Strict 8-term deep-module vocabulary with banned synonyms; the deletion test for pass-through modules; "one adapter means a hypothetical seam, two adapters means a real one"; interface-as-test-surface; the dependency-category → test-strategy table; design-it-twice as constraint-differentiated parallel subagents. Standalone, author-neutral. |
| `skill/prototype` | `skills/engineering/prototype/SKILL.md` (+ `LOGIC.md`, `UI.md`) | 5/5 | none (nearest: `brainstorming`, upstream of it) | **Adopt — genuine gap.** "A prototype is throwaway code that answers a question. The question decides the shape." Logic branch: pure reducer/state-machine behind a TUI shell with a purity firewall. UI branch: 3–5 structurally-different variants mounted on an *existing* route behind `?variant=` ("a throwaway route is a vacuum"), URL-backed switcher, NODE_ENV-gated. Capture-when-done: fold the decision into real code, commit the prototype to a throwaway branch as primary source. |
| `skill/resolving-merge-conflicts` | `skills/engineering/resolving-merge-conflicts/SKILL.md` | 3/5 | none | **Adopt — genuine gap, tiny.** Intent archaeology per conflicting hunk (commit messages → PRs → original issues), preserve-both-intents else pick by the merge's stated goal and note the trade-off, "do not invent new behaviour", always-resolve-never-abort, run the project's checks after. Our recurring cross-PR version races hit exactly this; nothing local covers conflict-resolution methodology. Note: upstream itself forgot to promote this skill (see findings) — adopt from the tree, not the manifest. |
| `skill/handoff` | `skills/productivity/handoff/SKILL.md` | 5/5 | none (nearest: `compound-docs`, different moment) | **Adopt — genuine gap, tiny.** Session-bridge document for a fresh agent: reference-not-copy rule (specs/plans/commits cited by path, never duplicated), suggested-skills routing metadata, temp-dir placement so handoffs never become workspace litter, explicit secret/PII redaction. Directly serves our multi-session lifecycle operating mode. |
| `skill/to-tickets` | `skills/engineering/to-tickets/SKILL.md` | 5/5 | `workflows:plan` (task lists), `file-todos`, lifecycle board | **Adopt, adapted to the lifecycle board (the costly part).** Context-window-sized tracer-bullet slices ("sized to fit in a single fresh context window" as the granularity criterion); blocking-edges-as-first-class-data enabling frontier scheduling; the expand–contract codification for wide refactors (expand ticket → blast-radius-sized migrate batches → contract ticket, integration branch only when batches can't stay green); the user calibration quiz; no-file-paths durability rule with the prototype exception. Retarget publishing from their tracker contract to `lifecycle_board.py` verbs. |

### skills — second wave (adopt after the first wave settles)

| ID | Upstream path @ HEAD | Quality | Local overlap | Recommendation |
|----|----------------------|---------|---------------|----------------|
| `skill/wayfinder` | `skills/engineering/wayfinder/SKILL.md` | 5/5 | lifecycle board (claims, stages), `workflows:plan` | **Adopt, second wave.** The most original skill in the source: multi-session planning as map + fog of war. Fog graduation test ("can you state the question precisely now, not answer it"); map-as-index (a decision lives in exactly one ticket; the map links); one-ticket-per-session hard rule; claim-before-work concurrency; refer-by-name legibility rule. Adopt after `to-tickets` settles the tracker-adaptation pattern; retarget `/grilling` to local interrogation skills. |
| `skill/diagnosing-bugs` | `skills/engineering/diagnosing-bugs/SKILL.md` (+ HITL template) | 5/5 | `debugging-and-error-recovery` (slot owner, PR #100 in flight), `reproduce-bug` | **Second wave, conditional.** Feedback-loop-first debugging: the 10-way loop-construction ladder, the red-capable/deterministic/fast/agent-runnable gate with pasted-output proof, 3–5 ranked falsifiable hypotheses before testing any, raise-reproduction-rate tactics for flaky bugs, the refusal protocol, tagged `[DEBUG-xxxx]` instrumentation. The debugging-slot owner is already slated for superpowers systematic-debugging enhancements (PR #108's mining plan); fold this source's ladder + gate into the same skill as a references file, and adopt standalone only if it doesn't fit there. |
| `skill/domain-modeling` | `skills/engineering/domain-modeling/SKILL.md` (+ ADR-FORMAT, CONTEXT-FORMAT) | 4/5 | `compound-docs` (solved problems; different artifact), codebase-memory `manage_adr` | **Adopt, second wave.** The ADR triple gate (hard-to-reverse AND surprising AND real trade-off, else no ADR); single-paragraph minimal ADR template ("the explicit no-s are as valuable as the yes-s"); CONTEXT.md glossary format with per-term `_Avoid_:` alias lists and the uniqueness inclusion test. Pairs with `codebase-design`. Reconcile file-location conventions with `compound-docs` and the codebase-memory ADR tooling at adoption time. |

## Mining notes (defer the component, lift the technique at next touch)

Each lift cites `Upstream-Ref` provenance like any adoption:

- **`skills/engineering/triage` → `lifecycle` + `file-todos` + `/triage`:** the two standout reference docs. **AGENT-BRIEF.md** ("the original body and discussion are context — the agent brief is the contract"): durability-over-precision (no file paths, no line numbers; interfaces/types/behavioural contracts instead), behavioral-not-procedural with paired good/bad examples, independently-verifiable acceptance criteria, explicit out-of-scope to prevent gold-plating — directly applicable to lifecycle-board item bodies. **OUT-OF-SCOPE.md**: a rejected-requests KB, one file per concept, with the poison-avoidance rule (already-implemented items are excluded so dedup checks stay honest) and durable-reason rule (deferrals aren't rejections). Also: verify-the-claim-before-grilling ordering, and the mandatory AI-disclaimer prefix on tracker writes. The state machine itself overlaps lifecycle stages; not adopted standalone.
- **`skills/productivity/grilling` → `brainstorming` + `document-review` + `interview-me`:** the facts-vs-decisions split ("facts findable in the codebase get looked up; the decisions are the human's" — added upstream precisely because autonomous frames read "explore instead of asking" as license to answer decisions themselves), recommended-answer-attached-to-every-question, and the explicit shared-understanding stop gate. 135 words total; the techniques fold in cleanly without adding a third interrogation skill to the trigger space.
- **`skills/productivity/writing-great-skills` → `create-agent-skills`:** context-load vs. cognitive-load as the single trade behind every authoring decision; leading-word (Leitwort) doctrine with the no-op grading test; completion-criterion two-axis model (clarity vs. demand); the negation failure mode ("prohibitions drag the banned behaviour into context — prompt the positive"); sentence-level pruning. Complements the superpowers writing-skills enhancement (empirical testing layer) already shortlisted into the same vehicle — this is the design-vocabulary layer; consider co-locating an adapted GLOSSARY.md. Note their negation finding and superpowers' Match-the-Form-to-the-Failure table agree from independent evidence.
- **`skills/engineering/code-review` → review agents + `workflows:review`:** the two-axis Standards/Spec split with the no-reranking rule ("separation stops one axis masking the other"); the inlined 12-smell Fowler baseline with "the repo overrides" and "always a judgement call" riders; fail-fast rev-parse + non-empty-diff gates before spawning reviewers; 400-word reviewer output cap.
- **`skills/engineering/tdd` → local `test-driven-development` (post-#104):** the pre-agreed-seams gate (user confirms test seams before any test exists) and the tautological-test rule (expected values from an independent source of truth; `expect(add(a,b)).toBe(a+b)` "passes by construction"). Also mocking.md's SDK-style-interfaces-over-generic-fetchers rule. Rides the same enhancement vehicle as the superpowers TDD mining notes.
- **`skills/engineering/to-spec` → `workflows:plan` + `prd`:** seam agreement at spec time; the no-file-paths spec-durability rule with the prototype exception (a snippet that "encodes a decision more precisely than prose can" rides along, trimmed).
- **`skills/engineering/setup-matt-pocock-skills` (tracker templates) → `lifecycle` docs:** the config-as-repo-docs indirection (skills speak canonical role names; one repo doc maps them to reality) and the Wayfinding-operations adapter vocabulary (map/child/blocking/frontier/claim/resolve) — an interface-with-three-adapters pattern worth remembering if lifecycle ever needs a second tracker backend.
- **`skills/misc/setup-pre-commit` → any future hook-setup skill:** the closing commit doubles as the smoke test of the hooks it just installed; conditional-omission with user notification.
- **`.out-of-scope/` repo pattern → this repo:** machine-discoverable negative decisions with prior-request citations, feeding triage dedup. Adjacent to our deferred-registry entries; worth considering for recurring user-facing feature requests.
- **`skills/deprecated/ubiquitous-language` → `compound-docs`:** the mandatory example-dialogue as glossary validation (a dev/domain-expert exchange proving the terms work in conversation).

## Deferred with strong local equivalents (no adoption, no mining urgency)

- `skills/engineering/research` — `deep-research` + researcher agents own the slot with far more machinery; the one-line citation discipline ("follow every claim back to the source that owns it") is already our posture.
- `skills/engineering/implement`, `grill-with-docs`, `productivity/grill-me` — deliberately thin orchestration shims over skills we're not adopting wholesale; their flow positions are already occupied by `workflows:work` and the brainstorm/interview surface.
- `skills/engineering/ask-matt`, `setup-matt-pocock-skills` (as a skill) — catalog router and Matt-branded setup; same verdict as superpowers using-superpowers and addyosmani session-start. Best flow documentation in the repo, adopted as nothing.
- `skills/engineering/improve-codebase-architecture` — proactive deepening scan + HTML report + grilling loop; entangled with `/grilling`, CONTEXT.md conventions, and CDN-loaded report chrome. The rejection-ADR loop-closer (record why a candidate was rejected so the next automated review doesn't re-surface it) and the glossary-terms-only Wins rule are noted for whenever we build a proactive architecture-review surface.
- `skills/productivity/teach` — the strongest stateful-workspace design in any triaged source (learning records as ADRs, mission gating, spaced retrieval), but personal-education domain; no core-plugin home, not enough for a domain plugin alone. Revisit if a learning/education domain plugin ever materializes.
- `skills/misc/git-guardrails-claude-code` — our committed hooks (`block-upstream-pr.sh`, block-no-verify, prevent-main-commit) cover this ground with sturdier matching; upstream's grep matcher is leaky/bypassable. Its verify-by-synthetic-stdin install step matches what our hook tests already do.
- `skills/misc/migrate-to-shoehorn`, `scaffold-exercises` — vendor-library codemod and private-tooling scaffolder; not portable.
- `skills/personal/*` (edit-article, obsidian-vault) — author-machine-specific.
- `skills/deprecated/*` — superseded upstream by promoted successors (design-an-interface → codebase-design DESIGN-IT-TWICE; qa/request-refactor-plan → triage/to-tickets chain; ubiquitous-language → domain-modeling); mined above where distinctive.
- `skills/in-progress/*` — explicitly not-ready upstream; `loop-me` is flagged for watching (adjacent to our loopy/loop-library surface: push-right checkpoint deferral, brief-not-raw-output), as is `claude-handoff` (depends on a `claude --bg` feature). Re-surface via `scan: auto` when they graduate buckets.
- `scripts/*` — maintainer symlink/list tooling; not applicable to marketplace distribution.

## Notable evaluation findings

- **Manual consistency drifts even for disciplined authors:** `resolving-merge-conflicts` violates the repo's own promotion invariant (in-tree + docs page, absent from plugin.json/READMEs/router), and the CHANGELOG documents a "Negative Space" failure mode that exists nowhere at HEAD. Validates our choice to enforce counts/parity mechanically in `tests/plugin-consistency.test.ts`.
- **The invocation doctrine is worth studying:** user-invoked skills orchestrate (zero context load, human as index), model-invoked skills hold reusable discipline, user→user composition impossible by construction, cross-skill dependency by prose invocation only (never file cross-links). Our skills mix these modes ad hoc; `create-agent-skills` could absorb the distinction.
- **The `.out-of-scope/` KB closes a loop we leave open:** rejected requests are recorded as machine-discoverable concepts with citations, so triage dedup gets honest negatives. Our registry does this for upstream components but nothing does it for feature requests.
- **`seam` threads their whole pipeline** (agreed in to-spec → tested at pre-agreed seams in tdd/implement → "the interface is the test surface" in codebase-design → "no correct seam is itself the finding" in diagnosing-bugs) — a vocabulary-driven coherence our pipeline achieves only via the lifecycle stages. The codebase-design + domain-modeling adoptions import the vocabulary layer that makes it work.
- **Convergent evidence across sources:** this repo, superpowers, and agent-skills independently arrive at one-question-at-a-time interrogation, no-file-paths durability rules, and behavior-shaping-over-prose skill styles — a strong signal those are load-bearing patterns, not house quirks.

## Bulk deferral

Everything in the mattpocock/skills tree at `391a2701dd948f94f56a39f7533f8eea9a859c87` **not
itemized above** is bulk-deferred at type level — recorded in `docs/upstream-sources.md` as a
single `all-unlisted @ 391a270…` entry. Future `/upstream-scan` runs suppress this baseline and
surface only new upstream components.

The shortlisted items are filed as individual `deferred:` entries with reason `shortlisted for
adoption: <why>` — actual adoption proceeds later, one human-reviewed adoption PR per item, each
repeating the full supply-chain gate (adapt-never-blind-copy, provenance pinning, version/count/
CHANGELOG bumps, `bun test`).
