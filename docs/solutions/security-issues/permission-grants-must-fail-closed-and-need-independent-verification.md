---
title: "Permission grants must fail closed on ambiguity, and the author is the wrong channel to verify that they do"
category: security-issues
tags: [permissions, clearance, autonomy, fail-closed, fail-open, labels, namespace, case-sensitivity, safe-default, independent-verification, self-review, guardrail, policy-test, agent-interpreted-policy]
module: plugins/agentic-engineering/scripts/lifecycle_board.py, plugins/agentic-engineering/skills/wf-development/references/workflows-orchestrate.md, plugins/agentic-engineering/skills/wf-development/references/escalation-contract.md, plugins/agentic-engineering/skills/wf-grooming/references/workflows-plan.md, tests/workflow-skill-architecture.test.ts
symptom: "A clearance label that authorized unattended agent execution resolved toward MORE autonomy in every ambiguous state — including the exact label a human would add to revoke it — and the first fix left a case-shaped hole in itself"
root_cause: "The writer and reader enumerated the known label instead of policing the namespace, so the design's safe-default asymmetry (absence means standard) was never carried through to conflict resolution; and the author verified their own safety fix, missing the same defect class twice"
---

# Permission Grants Must Fail Closed on Ambiguity, and the Author Cannot Verify That They Do

## Problem

PR #304 (issue #298) added a **delivery posture**: a `posture:autonomous` GitHub label that clears a
work item to run implementation → review → delivery with no human check-ins. The design was
explicitly asymmetric and, on paper, safe:

> `standard` is the safe default and writes **no** label, so unlabeled and legacy issues are standard
> for free.

Absence means "not cleared". That part was implemented correctly. What was never carried through is
what happens when the namespace holds something *other* than the one known label.

The writer computed the set of labels to strip by membership in the known-labels tuple:

```python
ALL_POSTURE_LABELS = ("posture:autonomous",)          # exactly one entry
present = [lbl for lbl in ALL_POSTURE_LABELS if lbl in current]
```

and the reader tested for that one label positively:

```python
return "autonomous" if POSTURE_LABELS["autonomous"] in labels else "standard"
```

Three consequences, all pointing the same direction — toward more autonomy:

```
start=['posture:standard'] apply='autonomous'
   removed_labels = []                                   # stray label survives
   edit = ['issue','edit','1','--add-label','posture:autonomous']   # now BOTH labels
start=['posture:standard'] apply='standard'
   edit = NONE                                           # stray label unremovable via the engine
resolve_posture(['posture:standard','posture:autonomous']) -> 'autonomous'
```

The third is the dangerous one. `posture:standard` is exactly what a human reaches for to
de-escalate a ticket in the GitHub UI — *adding* a label is the obvious gesture; *deleting* the
other one is not. So the single most likely human revocation gesture **granted** hands-off
execution. A fourth path had the same shape: on re-groom, an omitted `posture` left an existing
clearance intact while the grooming doc promised that answering "no" resolved to `standard`.

The writer's own docstring claimed the opposite of its behavior — *"strip any OTHER `posture:*` label
so an issue carries at most one"* — so anyone reasoning from the code's stated contract would have
concluded it was already correct.

### Then the fix repeated the defect

The first fix switched both sides to a namespace scan and made the reader safe-wins. It was
verified by its author — against a matrix the author chose — and it passed. An **independent**
verification pass then found the same class of hole one spelling narrower:

```
resolve_posture(['posture:autonomous', 'Posture:Standard']) -> 'autonomous'
```

`lbl.startswith("posture:")` is case-sensitive. GitHub treats label names case-insensitively for
uniqueness, so `Posture:Standard` is a label a human can genuinely create — and a case-sensitive
scan cannot see it. The fix for a fail-open shipped with a fail-open inside it.

The same pass found a second self-inflicted defect. A paragraph had been added to the escalation
contract specifically to stop it overstating security enforcement; that paragraph asserted *"the
engine returns a `blocked` verdict"* at the planning boundary. It does not: the gate verbs compute
`provenance` and never branch on it, and the only path returning `blocked`/`untrusted_provenance` is
reachable through a flag no route prescribes. The correction introduced a fresh false claim of the
exact kind it was written to remove.

## Solution

**Police the namespace, not the vocabulary.** Both sides now scan by prefix, case-insensitively, and
the reader treats *any* ambiguity as "not cleared":

```python
present = sorted(lbl for lbl in current
                 if lbl.lower().startswith(POSTURE_LABEL_PREFIX))

posture_labels = [lbl.lower() for lbl in labels
                  if lbl.lower().startswith(POSTURE_LABEL_PREFIX)]
return "autonomous" if posture_labels == [known] else "standard"
```

`== [known]` rather than `in` is the whole fix on the read side: cleared requires the known label to
be the *only* thing in the namespace. An unknown value from a future vocabulary, a case variant, a
conflicting pair — each resolves `standard`.

**A safety rule read through prose is implemented in the prose too — but that is a stopgap, not the
fix.** At #304 the routing boundary did not call the resolver at all; the plugin instructed an agent
to run `gh issue view <parent> --json labels` and interpret the result. A Python-only fix would
never have reached the boundary that actually gates autonomy, so the resolution rule was written
into `workflows-orchestrate.md` as well, leaving two copies that had to be kept consistent.

> **Superseded by #306 (PR #312).** Mirroring the rule into prose was the right *immediate* move and
> the wrong *resting place*: a safety property maintained in Python and Markdown at once is a
> property that drifts, and by #306 it had spread to three prose copies. The structural fix is to
> stop asking the model to apply the rule and give it a **machine-computed verdict** instead —
> `--groom-verify` now emits `cleared` (`groomed and posture == "autonomous"`) plus `posture_source`,
> and the boundary branches on those fields. The rule itself now lives in exactly one place,
> `resolve_clearance` in `lifecycle_board.py` (the `resolve_posture` named in the historical
> examples above was folded into it and removed). A guardrail in
> `tests/workflow-skill-architecture.test.ts` fails CI if any skill doc restates the rule again.
>
> The durable lesson is the ordering: mirror the rule into prose only while no machine-readable
> verdict is reachable, and treat that mirroring as debt to be repaid by computing the answer the
> model would otherwise have to derive.

**Verify safety fixes through a channel that did not produce them.** Every defect above was found by
an independent reviewer and missed by the author's own verification, twice.

## Prevention

- **Write the ambiguity table before the implementation.** For any permission mechanism, enumerate
  every state the namespace can hold — absent, known, unknown, conflicting, case-variant, malformed —
  and state the resolution for each. "Absence is safe" is not a design; it is one row of one.
- **Enumerate-the-known is a fail-open idiom.** Whenever a check asks "is the value I know about
  present?", the unhandled answer is everything else. For permissions, invert it: ask "is the
  namespace exactly what I wrote?" and deny otherwise.
- **Ask which gesture a human will actually make.** The revocation path here failed for the specific
  action a person is most likely to take (add a label) rather than the one the design assumed
  (delete a label). Model the UI affordance, not the API call.
- **Case-sensitivity is a security property when the input is human-typed.** Any identifier a person
  can create by typing — labels, tags, branch names — needs a case-folding decision made explicitly
  and tested, not inherited from whichever string method was reached for first.
- **A "documentation honesty" fix is a claim, and claims get verified.** The paragraph written to
  remove an overstatement introduced a new one. Check every assertion about enforcement against the
  code path it names, including — especially — assertions in the correction itself.
- **The author is not a verification channel for safety-critical changes.** Self-verification here
  passed three times against defects an independent pass found immediately. This is the same reason
  the escalation contract keeps a human near untrusted-provenance work: the party with the mental
  model that produced the gap cannot be the party that probes for it.
- **Mutation-test guardrails, do not merely add them.** The land-pr third of one fix was completely
  unguarded — deleting the change left the suite green. A guardrail that does not fail when the
  behavior regresses is worse than none, because it reads as coverage.
- **Two guardrail anti-patterns worth naming**, both found in this work's own tests:
  - *Hard-wrap-spanning literals.* `expect(doc).toContain("fails\ntoward `standard`")` embeds the
    file's line wrapping, so a pure reflow fails a test whose subject never changed. Normalize
    whitespace before matching.
  - *Negative assertions the corrected text still matches.* Banning `"silence or a no writes nothing,
    which resolves to `standard`"` also matched the *fixed* sentence once its qualifier was added.
    Assert the qualifier positively instead — require what must be true, rather than forbidding a
    phrase the correct text may legitimately contain.
- **Freeze categories, not spellings — and document the exceptions.** Repo policy is to assert the
  category. Where an external criterion genuinely requires verbatim text, say so in the test with a
  pointer to that criterion, so the brittleness reads as intentional.
- **Compute the verdict rather than restating the rule.** When a policy decision is made by a model
  reading a document, the fix is not a better-worded document — it is a field the engine emits that
  the model can branch on without re-deriving anything. Ask what single value the boundary actually
  needs, emit that, and let the prose point at it. Mirrored rules are a bridge to that, and a
  bridge left standing becomes the drift.

## Resources

- PR #304 — two-mode delivery posture; the review, fix, and verification commits (`ce07025e`,
  `bb543284`, `1b005872`).
- Issue #298 and sub-issues #299–#303 — the five-phase design and its acceptance criteria.
- Issue #306 — the follow-on: machine-enforce the attestation-AND-clearance conjunction instead of
  resolving it in prose, which is the structural version of the "prose is implementation" lesson.
- Issue #307 — bounded fail-safe edges recorded so a later contributor does not "fix" one into a
  fail-open.
- [Grep-based acceptance checks and subset fixtures give false confidence](../testing-patterns/grep-acceptance-checks-and-subset-fixtures-give-false-confidence.md)
  — the earlier instance of the same underlying failure: a check that passed on what it measured
  while being false of the repository.
