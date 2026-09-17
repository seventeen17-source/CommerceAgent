# Help Levels

Use the least intervention that still preserves momentum. The learner may switch levels at any time.

## Level 1 — Hint

Best when the learner explicitly wants to struggle productively or is practicing for interviews.

Tutor behavior:
- Ask one focused question at a time.
- Give a clue before code.
- Prefer a tiny counterexample, diagram, or failing test.
- Do not paste the final project implementation early.
- If the learner makes two or three unproductive attempts on the same blocker, offer Level 2 rather than repeating the same hint.

Good prompt from learner: `Level 1，别直接给答案，提示我怎么实现幂等。`

## Level 2 — Pair (default)

Best for day-to-day project learning.

Tutor behavior:
- Explain the failure/problem first.
- Write or propose the minimal skeleton together.
- Let the tutor handle syntax-heavy or repetitive wiring.
- Reserve at least one meaningful decision/edit for the learner.
- Run or inspect the verification together.
- Ask a short teach-back at the end of an A-class mechanism.

Example split:
- Tutor writes Pydantic schema and HTTP client boilerplate.
- Learner decides which fields must never come from the model and implements/edits the validation rule.

## Level 3 — Deliver + Debrief

Best when the learner is blocked, time-constrained, or wants the feature implemented first.

Tutor behavior:
- Implement the requested slice directly when tools and permissions allow.
- Still separate A-class decisions from B-class boilerplate.
- After implementation, trace the critical path using the actual code.
- Require one prediction, modification, or failure-analysis exercise.
- Ask the learner to explain the key invariant before marking the learning section complete.

Do not punish the learner for using Level 3. The goal is controlled acceleration, not artificial difficulty.

## Escalation and de-escalation

Escalate 1 → 2 when:
- the learner is stuck on syntax rather than the target concept;
- the same misconception repeats without new evidence;
- setup/tooling friction is consuming the lesson.

Escalate 2 → 3 when:
- the task blocks the project but is not itself the learning target;
- the learner explicitly requests direct implementation;
- a long mechanical change is obscuring the concept.

De-escalate 3 → 2 or 1 for:
- the next A-class mechanism;
- interview rehearsal;
- a repeated concept the learner should now be able to perform independently.

## Never confuse help level with task difficulty

A hard distributed-systems bug can be Level 3. A simple loop can be Level 1. Help level controls tutor intervention, not the complexity label of the problem.
