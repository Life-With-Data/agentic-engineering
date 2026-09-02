# UX psychology for conversion and onboarding surfaces

Behavioral principles for UI work items that carry a conversion, onboarding, or
commitment step. Grooming consults this to turn "how the surface should look"
into observable acceptance criteria for how it should behave. Review consults
the same file as a lens; see
[choose lenses](../../wf-review/references/workflows-review.md#choose-lenses).

Each principle below states the concept, the design move, and the shape of an
acceptance criterion that makes it verifiable. Write criteria as observable
behavior, never as "apply principle X".

## Ethics boundary: three principles are human-opt-in only

Endowed progress, loss-aversion framing, and anchoring/contrast are adjacent to
dark patterns. An agent never applies them unprompted. Each requires an explicit
human opt-in recorded in the work item, and each carries a truthfulness
constraint:

- **Real progress only.** A progress indicator reflects work the user has
  actually completed. Pre-filled steps must correspond to real state.
- **Truthful claims only.** Loss framing and anchor values state facts. No
  manufactured urgency, invented scarcity, or misleading comparison price.
- **No unprompted application.** Absent a recorded opt-in, groom the surface
  without these three and note that they were not applied.

The other three principles — smart defaults, reciprocity, and the IKEA effect —
reduce user effort without manufacturing pressure and need no opt-in.

## Smart defaults and decision-fatigue reduction

- **Concept:** every choice presented costs the user attention, and a long
  choice list raises abandonment more than it raises fit.
- **Design move:** pick a safe, reversible default for each decision the user
  does not need to make; collapse the rest behind a visible "change this"
  affordance; order options so the recommended one leads.
- **Criterion shape:** "Every field on the <flow> step has a pre-selected
  default; the user can complete the step without changing any of them; each
  default is reversible from <location>."

## Endowed progress (human-opt-in)

- **Concept:** a task shown as already begun is completed more often than the
  same task shown as untouched.
- **Design move:** frame a multi-step flow so steps the user has genuinely
  already satisfied — account created, email verified, plan chosen — are shown
  as complete rather than hidden.
- **Constraint:** the indicator reflects only real completed work. Never seed
  artificial progress.
- **Criterion shape:** "The <flow> progress indicator shows step N of M
  complete, where each completed step maps to a persisted user action;
  no step is marked complete without its backing state."

## Reciprocity: value before commitment

- **Concept:** users who receive something useful before being asked to commit
  are likelier to commit, and better qualified when they do.
- **Design move:** deliver a real, usable result — a preview, a report, a
  working sample — before the signup, payment, or contact-details gate.
- **Criterion shape:** "A user can reach <concrete value> without an account;
  the <gate> appears only after that value is delivered."

## IKEA effect: lightweight personalization

- **Concept:** users value what they helped build; small, cheap acts of
  configuration raise attachment and retention.
- **Design move:** offer one or two low-cost personalization steps whose result
  is immediately visible — naming a workspace, picking a starting template,
  choosing what appears first.
- **Constraint on cost:** personalization must stay optional and skippable, or
  it becomes decision fatigue and works against the first principle.
- **Criterion shape:** "The <flow> offers at most two optional personalization
  steps; each is skippable in one action; the chosen value is visible on the
  next screen."

## Loss-aversion framing (human-opt-in)

- **Concept:** a loss weighs more than an equivalent gain, so framing a choice
  around what is forgone can move behavior more than framing it around what is
  gained.
- **Design move:** where the statement is true, name the concrete thing the
  user keeps or gives up — unsaved work, an expiring trial's remaining data, a
  configured setup.
- **Constraint:** the loss must be real and accurately described. No invented
  deadlines, fake scarcity, or exaggerated consequences.
- **Criterion shape:** "The <exit/downgrade> confirmation names the specific
  artifacts affected and what happens to them; every stated consequence matches
  actual system behavior."

## Anchoring and contrast (human-opt-in)

- **Concept:** the first value a user sees frames how every later value is
  judged, and options are evaluated against their neighbors rather than in
  isolation.
- **Design move:** order a comparison set so the reference option appears
  first, and make the differences between adjacent options legible at a glance.
- **Constraint:** every anchor is a real, currently offered value. No struck-out
  price that was never charged and no comparison tier that cannot be purchased.
- **Criterion shape:** "The <comparison> presents options in <order> with the
  reference option first; every displayed value corresponds to a currently
  available offering."

## Applying this during grooming

For a UI work item with a conversion, onboarding, or commitment step:

1. Name which of the six principles the surface plausibly touches.
2. For each non-opt-in principle that applies, write an observable acceptance
   criterion in the issue body using the shapes above.
3. For each opt-in principle, do not apply it. If it looks valuable, surface it
   to the human as a question and record the decision — the recorded opt-in is
   what a reviewer later checks against.
4. Record principles considered and dismissed, so review does not re-raise them.
