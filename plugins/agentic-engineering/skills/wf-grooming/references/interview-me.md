# Interview Me

## Overview

What people ask for and what they actually want are different things. They ask for "a dashboard" because that's what one asks for, not because a dashboard solves their problem. They say "make it faster" without a number to hit.

The cheapest moment to find this gap is before any plan, spec, or code exists. Once building has started, switching costs are real, and the user will rationalize the wrong thing into a "good enough" thing. The misfit gets locked in.

This reference closes the gap before it costs anything. Downstream routes assume
the intent is already roughly known: the [brainstorming reference](brainstorming.md)
explores 2-3 approaches, the `wf-grooming` planning route turns the chosen one
into a plan, and `wf-review` can stress-test that plan. Interviewing happens
before all of those.

Position relative to `brainstorming`: interview-me nails down **what** the user truly wants (intent extraction); brainstorming explores **how** to build it (approach exploration). When an ask is underspecified, run interview-me first, then hand the confirmed intent to brainstorming. Their triggers are deliberately adjacent, so the ordering is what keeps them from colliding.

## When to Use

Apply this reference when:

- The ask is missing at least one of: **who** the user is, **why** they want it, what **success** looks like, what the binding **constraint** is
- The request is conventional rather than specific ("build me X", "make it faster") and the convention can't be unpacked without guessing
- There's a temptation to start with assumptions that haven't been surfaced
- The user hasn't said which value they're optimizing for when two reasonable ones are in tension (simplicity vs. flexibility, cost vs. speed)
- The user explicitly invokes: "interview me", "grill me", "before we start, are we sure?", "stress-test my thinking"

**When NOT to use:**

- The ask is unambiguous and self-contained ("rename this variable", "fix this typo")
- The user has explicitly asked for speed over verification
- Pure information requests ("how does X work?", "what does this code do?")
- Mechanical operations (renames, formats, file moves)
- Confidence is already ≥95%; re-read the stop condition below before assuming otherwise

## Loading Constraints

This reference needs a live, responsive user. **Do not invoke in non-interactive contexts** like CI pipelines, scheduled runs, `/loop`, or any autonomous loop. In one of those with an underspecified ask, flag that as a blocker for the user instead of guessing.

## The Process

### Step 1: Hypothesize, with a confidence number

Before asking anything, write down the current best read of what the user wants in **one sentence**, plus an honest confidence number (0–100%):

```
HYPOTHESIS: You want a way to answer "how are we doing?" in standup, and "dashboard" was the convention that came to mind.
CONFIDENCE: ~30% — missing: who it's for, what "metrics" means in context, and what success looks like
```

The number forces honesty. A high number that can't actually predict the user's reactions to the next three questions is wrong. Start at the confidence level that is defensible.

When confidence is below ~70%, append a brief reason on the same line — what's still unresolved or missing. This tells the user exactly what the interview needs to surface, and prevents the number from being a vague signal.

### Step 2: Ask one question at a time, each with a guess attached

Format:

```
Q: <one focused question>
GUESS: <a hypothesis for the answer, with the reasoning that produced it>
```

Wait for the user to react before asking the next question.

**Why one at a time, not a batch:**

- The user can't react to a hypothesis buried in a list
- Batches encourage skim-reading and surface answers
- The third question often depends on the answer to the first; asking them all at once locks in the wrong framing
- The user's energy for thinking carefully is finite; spend it one question at a time

**Why attach a guess:**

- The user reacts faster to a wrong guess than they generate an answer from scratch
- It commits to a hypothesis that can be visibly wrong, which keeps the interview honest
- It surfaces the *interviewer's* assumptions, which is what the interview is meant to expose

The risk here is a polite user agreeing with the guess to be agreeable. Mitigate by being visibly willing to be wrong, and occasionally guessing in a direction the user is expected to push back on.

### Step 3: Listen for "want vs. should want"

The most dangerous answers are the ones where the user says what a thoughtful answer *sounds like* rather than what they actually want. Watch for:

- Answers that pattern-match best-practice talk ("I want it to be scalable", "clean architecture") without specifics
- Answers that defer to convention ("the way most apps do it", "the standard approach")
- Phrases like "I should probably…", "I think I'm supposed to…", "good engineering practice says…"
- Buzzwords as goals — when "modern", "scalable", "robust" are the answer instead of a specific outcome

When one of these shows up, the question to ask is:

> *"If you didn't have to justify this to anyone, what would you actually want?"*

That single question often does more work than the previous five.

### Step 4: Restate intent in the user's own words

When confidence is high, write back what the user now appears to want. Keep it tight (5–8 lines), use their language where possible, and structure it so the user can confirm or correct line by line:

```
Here's what I now think you want:

- Outcome:      <one line>
- User:         <one line — who benefits>
- Why now:      <one line — what changed>
- Success:      <one line — how we know it worked>
- Constraint:   <one line — the binding limit>
- Out of scope: <one line — what we're explicitly not doing>

Yes / no / refine?
```

Including "Out of scope" is non-negotiable. Half of misalignment is silent disagreement about what is *not* being built.

### Step 5: Confirm — explicit yes, not "whatever you think"

The gate is an explicit "yes." The following are **not** yes:

- "Whatever you think is best." → The user is delegating, which means they don't have 95% confidence either. Re-ask with two concrete options framed as a choice.
- "Sounds good." → Ambiguous. Ask: "Anything you'd refine?" Silence isn't confirmation.
- "Sure, let's go." → Often a polite exit, not an endorsement. Same follow-up.
- Silence followed by "okay let's start." → The user has given up on the interview, not converged. Stop and ask whether something's been missed.

If the user corrects the restate, fold the correction in and restate again. Loop until there's an explicit yes.

### The 95% Confidence Stop

The interview is done when the answer to this is yes:

> *Can I predict the user's reaction to the next three questions I would ask?*

If yes, there's shared understanding. Stop interviewing and produce the restate. If no, the interview isn't done; ask the next question.

This is a checkable test, not a vibe. It also has a floor: several rounds in and still unable to predict is information about the ask, not a reason to keep grinding. Stop and tell the user: "I've asked X questions and I still can't predict your reactions. Something foundational is missing. Want to step back?"

## Output

The output of this reference is a **confirmed statement of intent**: the restate
from Step 4, with an explicit yes from Step 5. Hand it to the
[brainstorming reference](brainstorming.md), then to the `wf-grooming` planning
route when appropriate.

If the user wants the intent to persist for a multi-session project or handoff,
offer to save it in the GitHub work item. Only save after confirmation; do not
create a repository plan or brainstorm file.

## Example

```
User: build me a dashboard for our metrics

Agent:
HYPOTHESIS: You want a way to answer "how are we doing?" in standup, and "dashboard" came to mind because that's the conventional answer.
CONFIDENCE: ~30% — missing: who it's for, what "metrics" are, and what success looks like

Q:     Who's asking "how are we doing?" — you alone, the team in standup, or up the chain?
GUESS: engineering team in standup, because "we" usually scopes that way.

User: It's actually for me. I keep losing track of which experiments are running.
```

Two questions in, the actual ask turns out to be "a list of my experiments," not a dashboard — different artifact, different scope. Building the dashboard would have been wrong.

## Interaction with Other Routes

- **Brainstorming reference**: downstream within `wf-grooming`. Once intent is
  confirmed, use it to explore 2-3 concrete approaches.
- **the `wf-grooming` planning route** (this plugin): further downstream. When the confirmed intent is concrete enough to build ("I want X for Y users with Z success criteria"), the `wf-grooming` planning route turns it into an implementation plan and its own task breakdown. The intent statement this reference produces is the input that lets the `wf-grooming` planning route skip re-deriving what to build.
- **`wf-review` doubt-driven route**: opposite end of the timeline. Interviewing
  extracts intent before a decision; doubt-driven review challenges the artifact
  after a decision.

## Verification

After applying interview-me:

- [ ] An explicit hypothesis with a confidence number was stated in the first turn
- [ ] Every confidence number below ~70% was accompanied by a one-line reason (what's still unresolved or missing)
- [ ] Questions were asked one at a time, each with a guess attached
- [ ] At least one "what would you actually want if you didn't have to justify it?" probe ran when the user gave a sophistication-signaling or convention-signaling answer
- [ ] A concrete restate (Outcome / User / Why now / Success / Constraint / Out of scope) was written back to the user
- [ ] The user confirmed the restate with an explicit yes (not "whatever you think," not "sounds good," not silence)
- [ ] At the stop point, the next three questions' reactions were predictable
- [ ] Any handoff downstream (brainstorming or planning within `wf-grooming`) was framed in terms of the confirmed intent, not the original underspecified ask
