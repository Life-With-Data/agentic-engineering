# Run one ticket unattended

Take one ticket as far as authorized without routine check-ins.

## Select

Use the caller's ticket. If none was named, take the first item from:

```bash
python3 "<skill-directory>/scripts/lifecycle_board.py" --ready-work
```

The engine owns ordering. An empty list means there is no ready work.

## Run

1. Groom the item if its implementation scope or success criteria are unclear.
2. If grooming leaves the item at `planned`, record the unattended approval in
   the tracker and run:

   ```bash
   python3 "<skill-directory>/scripts/lifecycle_board.py" \
     --set-status <N> ready_for_work --force
   ```

   This is the sole self-approval path. Ordinary workflow routes wait for a
   human to move `planned` to `ready_for_work`.
3. Strip any `posture:*` label from the issue — a surviving label leaves the
   engine's `hands_off` verdict false and the dispatched stages re-gate the run:

   ```bash
   gh issue edit <N> --repo <owner/repo> --remove-label posture:standard
   ```

   Remove every label in the `posture:` namespace, whatever its spelling.
4. Invoke `wf-orchestrate` with autonomous posture and continue through
   delivery, including the required `wf-review` hop. Make reversible decisions
   from evidence, fix blocking failures, and do not ask between stages.
5. Keep repository-required checks and external safety constraints. Unattended
   mode does not authorize credentials, admin overrides, force-pushes, direct
   default-branch writes, destructive scope expansion, or unrelated work.
6. Record and surface a genuine unresolved blocker once, then stop or continue
   independent work as appropriate.

## Finish

Report the selected ticket, delivered state, verification evidence, deferred
work, and blockers. File a friction follow-up only when the run exposed a
specific, reusable problem with a concrete fix. Do not post a ritual
retrospective or hard-code a chat destination.
