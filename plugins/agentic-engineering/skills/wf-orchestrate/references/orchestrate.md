# Orchestrate engineering work

Move a request from its current state to the requested outcome. Workflow skills
are tools, not mandatory departments: use only the ones the work needs and keep
small transitions inline. The one exception is `wf-review`, which always runs
between development and delivery.

## Default posture

Proceed autonomously on reversible, in-scope decisions. Stop for:

- missing authority, credentials, or access;
- a material product or scope decision that repository evidence cannot settle;
- destructive or irreversible work outside the normal reviewed merge path;
- an external gate that cannot be cleared; or
- repeated attempts with no measurable progress.

The full safety boundary is in the [escalation contract](escalation-contract.md).
A `posture:standard` label requests more human involvement. Explicit invocation
arguments override that preference for the current run.

## Resolve the starting state

Use the request, repository state, and tracker state. In Project mode,
`lifecycle_board.py --groom-verify <N>` reports whether the item is groomed and
approved, plus its posture. For unattended execution, branch on its single
fused `hands_off` field — the engine owns that conjunction; never reassemble
it from the component fields or raw labels. A `planned` item routes to a human for the
`ready_for_work` stamp; only an approved item is ready to claim. Posture and
explicit invocation arguments affect interaction style, not this approval
boundary. `wf-auto` owns the explicit unattended exception.

- Unclear request or materially under-specified bug: use `wf-grooming`.
- Clear work that needs code or configuration changes: use `wf-development`.
- Change needing extra behavioral evidence: use `wf-testing`.
- A verified change awaiting delivery: use `wf-review`. It always runs next,
  before delivery, and scales its own depth to risk.
- Ready PR, CI repair, release, or deployment: use `wf-delivery`.
- Durable documentation requested or justified by a real reusable lesson: use
  `wf-documentation`.

Do not force an implemented change through separate testing and documentation
handoffs when development already produced credible evidence and the risk does
not justify them; `wf-review` still runs regardless.

## Execute

1. Validate repository context once, then load additional capabilities when
   first needed.
2. Establish the smallest clear scope and success check.
3. Claim tracked work at the development boundary.
4. Implement inline by default. Delegate only independent work that benefits
   from parallelism or an independent risk check.
5. Run focused checks while iterating and repository-required checks before
   delivery.
6. Route concrete failures back to the work that can fix them; do not bounce a
   task merely to satisfy stage ownership.
7. Deliver when required checks pass, blocking findings are resolved, the head
   is mergeable, and the run has merge authority.

## The ledger

A delegated run keeps one ledger, `ledger.md`, in the item's packet directory
alongside the briefs, reports, and review packages the run hands over as
files. It records, one line each: every ruling as what was decided, why, and
what it costs if wrong; every completed unit with its commit range; and every
fix round with what it addressed and what stayed open. Write the line when the
thing happens, not at the end.

The ledger is advisory resumption evidence and never a gate. Status is the
gate ([lifecycle](../../wf-setup/references/lifecycle.md)), exactly as it is
for a plan file or a packet.

On resume — after compaction, in a new session, or when another agent picks
the item up — read the board state first and let Status route the run. Then
read the ledger and re-dispatch only the units it does not show completed. A
unit the ledger records as complete is never re-run: its commits exist in
history whether or not the session remembers making them, and re-dispatching
a finished sequence is the most expensive way to lose a run.

## Review and documentation thresholds

`wf-review` always runs after development and before delivery; it is never
skipped. Independent review is expected for security-sensitive, data-destructive,
cross-cutting, or otherwise high-blast-radius changes. A concise self-review is
enough for routine localized changes unless repository policy says otherwise.

Capture durable knowledge only when the work revealed something non-obvious and
reusable that is not already enforced by code or tests. “Not needed” requires no
audit comment, document, or extra CI cycle.

## Completion

Report the delivered outcome, exact verification evidence, external state that
was read back, and any remaining risk or deferred work. Avoid stage-by-stage
travelogues.
