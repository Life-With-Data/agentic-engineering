/**
 * Single source of truth for the vendored-script bundle map.
 *
 * Each wf-* skill ships byte-identical copies of the canonical scripts it
 * depends on, so skills-only installs (`npx skills add ...`) stay
 * self-contained without symlinks (which dangle when a skill directory is
 * copied standalone). Keys are the file names bundled under
 * `skills/<owner>/scripts/`; values are the canonical source paths relative
 * to `plugins/agentic-engineering/`. When the canonical path already lives
 * inside the owning skill (e.g. wf-development's worktree-manager.sh), the
 * entry is the canonical itself and other skills vendor copies of it.
 *
 * Shared by tests/workflow-skill-architecture.test.ts (byte-identity gate)
 * and scripts/sync-skill-scripts.ts (the mechanical fixer). Edit the
 * canonical script, then run `bun run skills:sync` to refresh every copy.
 */

export type ScriptBundles = Record<string, Record<string, string>>

export const SCRIPT_BUNDLES: ScriptBundles = {
  "wf-grooming": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
  },
  "wf-development": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "workflow-repo-preflight.py": "scripts/workflow-repo-preflight.py",
    "worktree-manager.sh": "skills/wf-development/scripts/worktree-manager.sh",
  },
  "wf-testing": {
    "repository-context.py": "scripts/repository-context.py",
  },
  "wf-review": {
    "repository-context.py": "scripts/repository-context.py",
    "get-pr-comments": "skills/wf-review/scripts/get-pr-comments",
    "resolve-pr-thread": "skills/wf-review/scripts/resolve-pr-thread",
  },
  "wf-delivery": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "pr-landable-status": "skills/wf-delivery/scripts/pr-landable-status",
    "worktree-manager.sh": "skills/wf-development/scripts/worktree-manager.sh",
  },
  "wf-documentation": {
    "repository-context.py": "scripts/repository-context.py",
  },
  "wf-setup": {
    "repository-context.py": "scripts/repository-context.py",
    "lifecycle_board.py": "scripts/lifecycle_board.py",
    "bootstrap_lifecycle_board.py": "scripts/bootstrap_lifecycle_board.py",
    "config_registry.py": "scripts/config_registry.py",
    "block-db-push.py": "scripts/block-db-push.py",
    "block-no-verify.py": "scripts/block-no-verify.py",
    "block-slack-webhook.py": "scripts/block-slack-webhook.py",
    "hook_payload.py": "scripts/hook_payload.py",
    "prevent-main-commit.py": "scripts/prevent-main-commit.py",
  },
}
