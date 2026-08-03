---
title: "A guard that matches command phrasing is both evadable and false-blocking — read state, or move the control to the server"
category: security-issues
tags: [hooks, guardrails, git, branch-protection, false-positives, defense-in-depth]
module: prevent-main-commit
symptom: "The hook blocked the honest command, allowed every equivalent one, and blocked a required delivery step"
root_cause: "The push rule grepped the command string for a literal `main` token, deciding from the shape of the phrasing rather than from what the command would actually do"
---

# Client-Side Guards Must Read State, Not Phrasing

## Problem

`prevent-main-commit.py` enforced two rules that looked alike and were not.

The **commit** rule read live repository state:

```python
is_commit and current_branch() in PROTECTED_BRANCHES
```

The **push** rule grepped the command string for a literal `main`/`master`
token. Driving the hook as a subprocess in a throwaway repo, on branch `main`:

```
BLOCK  git push origin main
allow  git push
allow  git push origin HEAD
allow  git push --force origin HEAD
```

All four update remote `main`. The guard stopped the one written honestly and
passed every equivalent phrasing — including the only genuinely destructive one.
It was **too loose**: evadable by rewording, not by privilege.

It was simultaneously **too tight**. `git push origin main` is a required step of
the delivery lifecycle on forges without a pull-request flow (commit on a branch
→ merge into `main` → push). The guard hard-blocked the one push that was
supposed to happen.

The failure mode is vivid: while opening the PR that removed this rule, the
still-installed hook **blocked `gh pr create`** — because the PR body quoted the
reproduction table above. It was matching prose in a heredoc. A guard that
inspects text will eventually block text.

## Root cause

Two different questions were being answered by one script:

1. *Is this process about to create a commit on a protected branch?* — answerable
   from repository state, cheaply and exactly.
2. *Would this push move a protected ref?* — **not** answerable from the command
   string. It depends on the current branch, the configured upstream, `push.default`,
   and refspec resolution. A regex over the argv approximates it, and every
   approximation is both a false negative and a false positive.

Question 2 already had a correct answer elsewhere: the forge. Server-side
protection binds every client, every identity, and every phrasing:

- buzz: `buzz repos protect set --ref refs/heads/main --push owner --no-force-push`
- GitHub rulesets: `pull_request`, `non_fast_forward`, `deletion`,
  `required_linear_history`

## Solution

Delete the push rule and the machinery that existed only to serve it
(`pushes_to_protected`, `SEGMENT_SPLIT`, `split_segments`). Keep the commit rule,
which reads state and cannot be evaded by rewording. Document the removal as
deliberate, with the server-side control named, so it is not "restored" later as
an apparent gap.

The stated intent — *no direct commits to a protected branch* — was already fully
enforced by the rule that survived. The deleted rule added no coverage; it added
evasion surface and a blocked lifecycle step.

## Prevention

- **Ask what the guard reads.** A check that reads repository or process state
  can be exact. A check that reads the command string is a heuristic wearing a
  guarantee's clothing. Prefer the former; when only the latter is available,
  size your confidence accordingly.
- **A client-side check cannot be a security control.** It is a typo-catcher for
  a cooperating operator. Anything that must actually bind belongs where the
  operator cannot rephrase past it. Do not duplicate a server-side control
  client-side and count it twice.
- **Never place a heuristic guard on a required lifecycle path.** The cost of a
  false positive there is not an annoyance — it blocks delivery, and it trains
  everyone to reach for a bypass flag.
- **Test guardrails by category, not by literal** — and check that the category
  is real. Asserting over a generated corpus (flag × remote × refspec) instead of
  a frozen list is necessary but not sufficient: a product of hand-frozen tuples
  is still an enumeration, just a longer one. The first version of this PR's
  corpus spelled every qualified form for `main` but only the bare form for
  `master`, and included `--force` but not `-f`. Mutation testing found three
  plausible reintroduced checks that passed it clean — including a force-push
  guard spelled `-f`, the single most likely reintroduction of all.
- **Verify a guardrail suite by mutating the guard, not by reading the tests.**
  Reintroduce the check the tests exist to forbid and confirm the suite goes
  red. Two of this hook's tests looked protective and were not: a source-text
  assertion that the deleted helpers are absent passed against the full old rule
  restored under renamed helpers, and no test pinned that the protected-branch
  set is matched by equality until one was added — a substring match let
  `main-feature` be treated as `main` with the suite still green.
- **A guard that scans text will block prose about itself.** Commit messages, PR
  bodies, heredocs, and documentation all flow through the same argv. Strip
  quotes *and* heredocs, or accept that writing about the rule will trip it —
  this hook strips quotes only, so a heredoc PR body discussing a commit still
  false-blocks while on `main`.

## Resources

- Fixed in: PR #362 (issue #359)
- Hook catalog: [`plugins/agentic-engineering/scripts/HOOKS.md`](../../../plugins/agentic-engineering/scripts/HOOKS.md)
  records the removal under "Not blocked, deliberately"
