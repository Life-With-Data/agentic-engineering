---
name: lfg
description: Full autonomous engineering workflow
argument-hint: "[feature description]"
disable-model-invocation: true
---

Run these slash commands in order. Do not do anything else. Do not stop between steps — complete every step through to the end.

1. **Optional:** If the `ralph-wiggum` skill is available, run `/ralph-wiggum:ralph-loop "finish all slash commands" --completion-promise "DONE"`. If not available or it fails, skip and continue to step 2 immediately.
2. `/workflows:plan $ARGUMENTS`
3. `/agentic-engineering:deepen-plan`
4. `/workflows:work`
5. `/workflows:review`
6. `/agentic-engineering:resolve_todo_parallel`
7. `/agentic-engineering:test-browser`
8. `/agentic-engineering:feature-video`
9. Land the PR: run the `land-pr` skill in autonomous mode — it waits for CI to go green, resolves any remaining review threads, and **auto-merges** once CI is green, the multi-agent review from step 5 left no open P1s, and all threads are resolved, then deletes the branch and confirms the tracker item is closed. The merge gate is the review you already ran in step 5 — do **not** wait for a human GitHub approval. Only stop if a condition genuinely can't be met (CI stuck red after retries, or branch protection requires something you can't supply).
10. Output `<promise>DONE</promise>` once the PR is merged.

Start with step 2 now (or step 1 if ralph-wiggum is available).
