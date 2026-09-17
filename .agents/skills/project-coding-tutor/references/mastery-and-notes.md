# Mastery Checks and Learning Notes

## Mastery is behavioral

Do not mark a concept mastered because the learner says “懂了”. Look for evidence that the learner can explain, predict, modify, and debug it.

A useful four-level rubric:

- **0 — Seen:** recognizes the term only.
- **1 — Explain:** can state the purpose and basic flow.
- **2 — Apply:** can make a small correct change and verify it.
- **3 — Debug/Defend:** can reason about failure modes, alternatives, and interview questions.

For important project concepts, target level 2 during implementation and level 3 before interview review.

## Fast mastery check

Choose 2–4, not all:

1. Explain the mechanism without reading the code.
2. Point to the source of truth.
3. Predict what happens under one failure.
4. Identify one unsafe/simpler implementation and why it fails.
5. Change one condition or parameter and predict the test impact.
6. Name the test that proves the invariant.
7. Explain the design in 30–60 seconds as if answering an interviewer.

## Milestone learning note template

When a meaningful section or milestone finishes, produce or update a note like:

```markdown
# [Milestone / Topic]

## What I built
- [verified behavior, not vague technology list]

## Core flow
`input → component → decision → write/side effect → verification`

## A-class concepts I learned
### [Concept]
- Problem it solves:
- Source of truth / owner:
- Key invariant:
- Failure mode:
- Test/evidence:
- Java analogy (if useful):
- Where the analogy breaks:

## Mistakes / bugs I hit
- Symptom:
- Wrong hypothesis:
- Actual cause:
- Debugging heuristic:

## What I can now do without copying
- [specific behavior]

## Still weak / revisit later
- [specific gap]

## Interview answers
- Q:
  - 30-second answer:
- Q:
  - 30-second answer:

## Evidence
- branch/tag/commit:
- tests/commands:
- relevant files:
```

Do not fill unknown evidence with invented values.

## Spaced revisit

When the same concept appears later:
- first ask the learner to recall the old mechanism;
- let them attempt before re-explaining;
- compare the new use case with the previous one;
- update mastery level only after new evidence.

Repeated exposure should require less tutor intervention over time.
