---
name: slfg
description: Full autonomous engineering workflow using swarm mode for parallel execution
argument-hint: "[feature description]"
disable-model-invocation: true
---

Swarm-enabled LFG. Run these steps in order, parallelizing where indicated. Do not stop between steps — complete every step through to the end.

## Sequential Phase

1. **Optional:** If the `ralph-wiggum` skill is available, run `/ralph-wiggum:ralph-loop "finish all slash commands" --completion-promise "DONE"`. If not available or it fails, skip and continue to step 2 immediately.
2. `/workflows:plan $ARGUMENTS`
3. `/agentic-engineering:deepen-plan`
4. `/workflows:work` — **Use swarm mode**: Make a Task list and launch an army of agent swarm subagents to build the plan

## Parallel Phase

After work completes, launch steps 5 and 6 as **parallel swarm agents** (both only need code to be written):

5. `/workflows:review` — spawn as background Task agent
6. `/agentic-engineering:test-browser` — spawn as background Task agent

Wait for both to complete before continuing.

## Finalize Phase

7. `/agentic-engineering:resolve_todo_parallel` — resolve any findings from the review
8. `/agentic-engineering:feature-video` — record the final walkthrough and add to PR
9. Land the PR: run the `land-pr` skill in autonomous mode — wait for CI to go green, resolve any remaining review threads, and **auto-merge** once CI is green, the multi-agent review from step 5 left no open P1s, and all threads are resolved, then delete the branch and confirm the tracker item is closed. The merge gate is the review you already ran in step 5 — do **not** wait for a human GitHub approval. Only stop if a condition genuinely can't be met (CI stuck red after retries, or branch protection requires something you can't supply).
10. Output `<promise>DONE</promise>` once the PR is merged.

Start with step 1 now.
