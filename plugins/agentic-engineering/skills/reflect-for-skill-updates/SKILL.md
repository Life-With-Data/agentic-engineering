---
name: reflect-for-skill-updates
description: Turn debugging sessions and workflow mistakes into permanent skill improvements. Use after fixing a bug that missing documentation would have prevented, discovering a gotcha, or finishing any session where the tooling let you down.
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
---

# Reflect for Skill Updates

> **Purpose**: Turn debugging sessions and mistakes into permanent improvements — updating skills, CLAUDE.md, hooks, and automation so the same problem never costs time twice.

This is the meta-improvement loop for the **agentic engineering** workflow. Where `/workflows:compound` captures the solution to a technical problem, this skill captures *what was missing from the tooling or documentation that let the problem occur in the first place*.

## Quick Reference

| Fix Category | Where to Update |
| ------------ | --------------- |
| Skill missing a step | Relevant `SKILL.md` — add to workflow or troubleshooting |
| Undocumented gotcha | Skill troubleshooting section or CLAUDE.md |
| Missing automation | Project scripts, hooks, or Makefile targets |
| Missing validation | Pre-commit hooks or CI checks |
| Wrong mental model | Skill introduction or conceptual overview |
| Undocumented dependency | Skill prerequisites section |
| Missing workflow step | Update the skill's numbered procedure |

## Reflection Process

### Step 1: Identify the Root Cause

Ask:

1. **What went wrong?** (Symptom)
2. **Why did it go wrong?** (Root cause)
3. **What knowledge would have prevented it?** (Missing documentation)
4. **Where should that knowledge live?** (Skill, CLAUDE.md, hook, script)

### Step 2: Categorize the Fix

| Category | Example | Where to Fix |
| -------- | ------- | ------------ |
| **Missing automation** | Env files weren't synced to worktrees | Setup script or worktree-manager |
| **Missing validation** | No check for port conflicts | Pre-commit hook or setup script |
| **Incomplete skill** | Skill didn't cover the edge case you hit | `.claude/skills/<skill>/SKILL.md` or `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/SKILL.md` |
| **Missing troubleshooting** | Common error not documented | Add to skill's Troubleshooting section |
| **Configuration drift** | Env files got out of sync | Add consistency checks to setup scripts |
| **Missing workflow step** | Forgot a required command | Update the skill's numbered procedure |
| **Undocumented dependency** | Feature X only works when Y is configured | Prerequisites section of the relevant skill |

### Step 3: Implement the Fix

#### For Skill Updates

```bash
# Find the relevant skill — check the plugin skills and any local project skills
ls ${CLAUDE_PLUGIN_ROOT}/skills/
ls .claude/skills/ 2>/dev/null || true

# Read and update
cat ${CLAUDE_PLUGIN_ROOT}/skills/<skill-name>/SKILL.md
```

Edit the skill to add:
- A Troubleshooting entry for this class of error
- A Prerequisites note if something must be configured first
- A Warning/Note if the step is commonly skipped
- A complete workflow step if one was missing

#### For CLAUDE.md Updates

Add to the project's CLAUDE.md:
- Key Learnings section entry for the session
- Cross-reference to updated skills
- Any configuration or tooling assumptions that bit you

#### For Hook / Automation Fixes

If a hook would have caught this (a `--no-verify` bypass, a direct push to main, a bad migration command), consider adding or improving a PreToolUse hook in `.claude/settings.json`.

### Step 4: Verify the Fix

1. Would this change have prevented the original issue?
2. Is the fix in the right place? (Where would someone look for this?)
3. Is it discoverable? (Clear headings, keywords, troubleshooting section)
4. Does it explain the *why*, not just the *what*?

## Reflection Template

```markdown
## Issue Encountered
[Brief description of what went wrong]

## Root Cause
[Why it happened — the underlying reason]

## Impact
[Time wasted, confusion caused, potential for recurrence]

## Fix Applied
[What was changed and where]

## Prevention
[How this fix prevents future occurrences]
```

## Common Patterns to Watch For

### Missing Prerequisites

**Pattern**: A skill assumes something exists (a tool, env var, service) but doesn't verify it.
**Fix**: Add a Prerequisites section with explicit checks and helpful error messages.

### Silent Failures

**Pattern**: Something fails with no visible error message.
**Fix**: Add logging, monitoring, or output validation that surfaces the failure immediately.

### Configuration Consistency

**Pattern**: Two components expect the same value but use different sources, drifting apart.
**Fix**: Add a consistency check in the setup script or CI.

### Undocumented Dependencies

**Pattern**: Feature X only works when Y is configured, but Y isn't mentioned in X's docs.
**Fix**: Document the dependency in X's Prerequisites section and cross-link.

### Workflow Gaps

**Pattern**: A step is missing from documented procedures (e.g., "run dev server" but doesn't say to kill old processes first).
**Fix**: Update the workflow with complete steps, including cleanup and precondition steps.

## Example Reflection

**Issue**: Worktree had stale env vars because the setup script didn't copy `.env.local`.

**Root Cause**: `worktree-manager.sh` only copied `.env` — not `.env.local` — so the worktree ran against the wrong database.

**Impact**: ~30 minutes debugging a "table not found" error that only appeared in the worktree.

**Fix Applied**:
1. Updated `SKILL.md` for the `git-worktree` skill to document that `.env.local` must be present and how to copy it manually if missing.
2. Added a `copy-env` subcommand to `worktree-manager.sh` that copies all `*.env*` files.
3. Added a note in the Troubleshooting section: "If you see database errors only in a worktree, check that `.env.local` was copied."

**Prevention**: Future worktree setup explicitly mentions env file copying. A manual workaround is documented and the script handles it automatically.

## When to Use This Skill

Invoke after:

- A bug was caused by **missing or incomplete documentation**
- You had to **debug something a skill should have prevented**
- Configuration was **inconsistent** between environments
- A workflow step was **missing** from documented procedures
- You discovered a **gotcha** others will hit too
- Any session where you caught yourself thinking "I should have known to do X"

**Activation keywords**: reflect, skill update, documentation gap, prevent this mistake, improve skills, lessons learned, skill improvement, documentation update, gotcha, post-mortem, knowledge capture, what did we learn, update SKILL.md, missing documentation, skill gap

## Related Skills

- **compound-docs**: Captures the *solution* to a problem; this skill captures what *tooling/documentation gap* allowed it
- **create-agent-skills**: Best practices for writing new skills
- **skill-creator**: Step-by-step guide to creating a new skill from scratch
- **setup**: Reconfigure which agents and integrations are active for this project
