---
title: "A change can falsify a compounded learning, and no CI check will tell you — grep the `module:` backlinks"
category: process
tags: [compounding, docs-solutions, stale-docs, learnings-researcher, module-frontmatter, superseded, doc-health, backlink]
module: docs/solutions/
symptom: "A merged change silently inverted the central lesson of an existing docs/solutions entry, leaving the compounding layer teaching the opposite of the shipped code"
root_cause: "docs/solutions entries record a conclusion that was true at a point in time, but nothing links a code change back to the entries whose lesson it invalidates — the module: frontmatter already names the coupling and no check reads it"
---

# Compounded Learnings Go Stale Silently

## Problem

PR #312 (issue #306) replaced a prose-mirrored safety rule with a machine-computed verdict: the
routing boundary stopped re-deriving delivery-posture clearance from labels and started reading a
`cleared` field the engine emits.

The learnings doc from the *previous* PR in the same area
([[permission-grants-must-fail-closed-and-need-independent-verification]]) had recorded the opposite
conclusion as current practice:

> **A safety rule read through prose is implemented in the prose too.** [...] the code is not the
> single source of truth when a model is the interpreter.

That was true when written. PR #312 made it false. The doc also named `resolve_posture`, a function
the same PR deleted.

Nothing flagged it:

- `docs/solutions/` has no PR-time check. `.github/workflows/doc-health.yml` was `schedule` +
  `workflow_dispatch` only — and was itself calling a scanner deleted in #233, so it had been failing
  on cron since (issue #313). That workflow was deleted outright in #367; the gap it left unguarded
  is unchanged, because it had not guarded anything since #233.
- `bun test`, `typecheck`, `docs:check`, and `skills:check` do not read `docs/solutions/`.
- The change's own guardrail tests passed, because they guard the *skill docs*, not the learnings.

The failure mode is worse than a merely outdated doc. `learnings-researcher` exists to surface
`docs/solutions/` as prior art during grooming. A future posture-adjacent work item would have hit
that entry, concluded the resolution rule belongs duplicated in prose, and re-introduced the exact
duplication PR #312 removed — which the new guardrail then rejects. The compounding layer would have
been actively arguing against the codebase, with CI as the only thing saying no.

## Solution

**The coupling is already recorded — read it.** Every `docs/solutions/` entry carries a `module:`
frontmatter field naming the files its lesson is about. That is a backlink nobody was following. One
grep over the changed files answers "did I just falsify a recorded lesson?":

```bash
for f in $(git diff --name-only main...HEAD); do
  grep -l "$f" docs/solutions/**/*.md docs/solutions/*.md 2>/dev/null
done | sort -u
```

Run it before merge. For each hit, open the doc and decide: still true, needs a superseded note, or
needs the symbol names refreshed. On PR #312 this returned two docs — one genuinely falsified, one
(`skills-mutating-user-repos-git-gotchas`, which names `read_board_config`) untouched and still
accurate. Both outcomes are useful; the check is cheap and its false-positive cost is one file read.

**Supersede, do not rewrite.** The incident narrative in an existing entry is still true history and
deleting it destroys the evidence for why the guidance existed. Mark the specific superseded claim
in place, name what replaced it and where, and state the *ordering* lesson that reconciles the two.
On PR #312 the reconciliation was: mirroring a rule into prose is correct only while no
machine-readable verdict is reachable, and that mirroring is debt to be repaid by computing the
answer the model would otherwise derive. Both PRs were right for their moment; only the sequence is
the durable lesson.

**Note renamed symbols where the old name appears.** Historical code samples should keep the name
they actually had — changing them falsifies the history — but the entry needs one line saying the
symbol was later renamed or folded, so a reader grepping for it does not conclude the doc is fiction.

## Verification

```bash
# The backlink check itself, over this change:
for f in $(git diff --name-only main...HEAD); do
  grep -l "$f" docs/solutions/**/*.md docs/solutions/*.md 2>/dev/null
done | sort -u
```

Expected: every returned path has been opened and dispositioned in the same PR.

## Prevention

- **Make the backlink check part of the pre-merge compounding gate**, not a thing to remember. The
  `wf-delivery` land route already runs a mandatory final compounding disposition immediately before
  merge; the `module:` grep is the mechanical half of that judgment and costs one command.
- **A cron-only doc check is not a check.** `doc-health.yml` running weekly meant its own breakage
  went unnoticed indefinitely (#313), and it was eventually deleted rather than repaired (#367).
  Anything meant to protect a durable invariant belongs on the PR path, where it fails in front of
  the person who caused it.
- **A check that cannot fail is worse than no check.** That workflow's agent tier ran `continue-on-
  error` and gated on a structured output the agent never produced, so `jq -r '.must_fix // false'`
  reported "No must-fix issues" from an empty string every week. Verify a gate by making it fire —
  if no input can turn it red, it is reporting your intentions, not your repository.
- **`module:` is load-bearing metadata, so keep it accurate.** An entry whose `module:` list omits a
  file it actually reasons about is invisible to this check. When amending a solution doc, re-check
  that its `module:` still names every file the lesson depends on.
- **Treat a superseded lesson as a finding, not a chore.** It is worth blocking a PR for: an
  inverted lesson in the compounding layer is read by agents as authoritative prior art, and its
  cost is paid later, by someone who will not know to doubt it.
- **The generalization beyond this repo:** any knowledge store that agents consult as prior art needs
  an invalidation path from the code it describes. Recording the coupling (as `module:` does) is half
  the work; the other half is a step that actually traverses it.

## Resources

- PR #312 / issue #306 — the change that falsified the entry; the superseded note it added.
- PR #304 / issue #298 — the entry that was falsified, and why its conclusion was right at the time.
- Issue #313 — `doc-health.yml` calling a scanner deleted in #233, the reason no automated check
  existed.
- [[permission-grants-must-fail-closed-and-need-independent-verification]] — the superseded entry.
