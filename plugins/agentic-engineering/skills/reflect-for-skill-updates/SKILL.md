---
name: reflect-for-skill-updates
description: Turn debugging sessions and workflow gaps into permanent skill improvements. Use after resolving bugs, hitting missing documentation, or discovering gotchas that others will likely encounter.
allowed-tools:
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - Bash
---

# Reflect for Skill Updates

> **Purpose**: When a debugging session, workflow gap, or discovered gotcha reveals missing knowledge, capture it permanently by updating the relevant skill — making the next occurrence a lookup, not a re-investigation.

This skill is the compounding step that closes the loop: after `/workflows:compound` captures a *solved problem*, this skill updates the *skills themselves* so future agents start with the right knowledge baked in.

## Quick Reference

| Fix Category | Where to Update |
| ------------ | --------------- |
| Missing automation | Plugin `scripts/` directory |
| Missing validation | Hooks (`plugin.json → hooks`) |
| Incomplete skill | `skills/<skill-name>/SKILL.md` |
| Common troubleshooting | Add to skill's Troubleshooting section |
| Missing workflow step | Update skill's workflow steps |
| Command gaps | `commands/*.md` |

## Reflection Process

### Step 1: Identify the Root Cause

Ask:

1. **What went wrong?** (Symptom)
2. **Why did it go wrong?** (Root cause)
3. **What knowledge would have prevented it?** (Missing documentation)
4. **Where should that knowledge live?** (Skill, command, hook, CLAUDE.md, etc.)

### Step 2: Categorize the Fix

| Category | Example | Where to Fix |
| -------- | ------- | ------------ |
| **Missing automation** | Validation step wasn't scripted | `scripts/` in the plugin |
| **Missing validation** | No check for a common prerequisite | Add a hook or preflight script |
| **Incomplete skill** | Skill didn't cover an edge case | `skills/<skill>/SKILL.md` |
| **Missing troubleshooting** | Common error not documented | Add to skill's Troubleshooting section |
| **Configuration drift** | Two components used inconsistent values | Add consistency check |
| **Missing workflow step** | A command's steps were incomplete | Update `commands/<command>.md` |

### Step 3: Implement the Fix

#### For Skill Updates

```bash
# Find the relevant skill
ls skills/

# Read the current skill
cat skills/<skill-name>/SKILL.md

# Update with new information:
# - Add to troubleshooting section
# - Add to edge cases
# - Update workflow steps
# - Add warnings/notes
```

#### For Command Updates

```bash
# Find the relevant command
ls commands/

# Update the command with the missing step or clarification
cat commands/<command>.md
```

#### For Hook Additions

When the fix is "this should never be allowed," add a PreToolUse hook in `plugin.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<new-hook>.py" }
        ]
      }
    ]
  }
}
```

### Step 4: Verify the Fix

1. **Would this have prevented the original issue?**
2. **Is the fix in the right place?** (Where would someone look for this?)
3. **Is it discoverable?** (Clear headings, keywords, troubleshooting sections)
4. **Does it explain the "why"?** (Not just what to do, but why it matters)

## Reflection Template

Use this when capturing a lesson:

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

**Pattern**: A skill or command assumes something exists but doesn't verify it.
**Example**: A skill assumes a tool is installed but never checks.
**Fix**: Add a prerequisite check and a helpful error message at the start of the skill.

### Undocumented Dependencies

**Pattern**: Feature X only works if Y is configured, but Y isn't mentioned.
**Example**: A skill requires an environment variable that isn't documented.
**Fix**: Document the dependency explicitly, with a note on how to set it up.

### Silent Failures

**Pattern**: Something fails but there's no visible error.
**Example**: A script exits 0 on error; the user sees no output and can't diagnose the issue.
**Fix**: Add explicit validation and surfaced error messages.

### Workflow Gaps

**Pattern**: Steps are missing from documented procedures.
**Example**: A command's instructions omit a step that's always required.
**Fix**: Update the command with the complete sequence of steps.

### Configuration Consistency

**Pattern**: Two components use different values for the same thing.
**Example**: Two skills reference different paths for the same resource.
**Fix**: Canonicalize the value in one place and reference it from both.

## Example Reflection

**Issue**: The `test-strategy-reviewer` agent was invoked but didn't know where to find integration tests in a new project structure.

**Root Cause**: The skill only documented the default convention (`spec/` for Rails, `tests/` for Python) but not how to override it for non-standard layouts.

**Impact**: ~15 minutes of manual path discovery before the agent could run usefully.

**Fix Applied**:
1. Updated `skills/test-strategy-reviewer/SKILL.md` to add a "Project Layout" section with override instructions
2. Added a troubleshooting entry: "Agent can't find tests → tell it the test directory explicitly"

**Prevention**: The skill now prompts users to provide the test root if using a non-standard layout.

## Skills Commonly Needing Updates

| Skill | Common Gaps |
| ----- | ----------- |
| `orchestrating-swarms` | New orchestration patterns, agent coordination edge cases |
| `compound-docs` | New categorization schemes, updated templates |
| `file-todos` | New tracker integrations, workflow sequence changes |
| `linear-sync` | API changes, new sync edge cases |
| `git-worktree` | Environment setup, port conflicts, isolation patterns |
| `test-strategy-reviewer` | New testing frameworks, project layout variations |
| `brainstorming` | Facilitation gaps, new exploration patterns |
| `frontend-design` | Updated component patterns, new design system conventions |

## When to Use This Skill

Invoke when:

- A bug was caused by **missing or incomplete documentation** in a skill
- You had to **debug something that a skill should have caught**
- You discovered a **gotcha** that others will likely hit too
- A **workflow step was missing** from a command
- The user explicitly asks: "Any skills need updating?" or "Should we capture this?"

**Activation keywords**: reflect, skill update, documentation gap, prevent this mistake, improve skills, lessons learned, skill improvement, documentation update, update skill, skill gap, gotcha, post-mortem, post-implementation review, knowledge capture, what did we learn, update SKILL.md, missing documentation
