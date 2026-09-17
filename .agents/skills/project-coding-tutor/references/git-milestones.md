# Git Milestones and Learning Milestones

Use Git structure to preserve project history and make learning checkpoints concrete, but do not confuse Git operations with learning itself.

## Recommended semantics

- `dev/...` — active development line;
- `milestone/...` — verified, intentionally stable snapshot;
- `fix/...` — repair from a known stable point;
- `experiment/...` — temporary technical exploration;
- `archive/...` — historical research/design reference.

Do not create a branch for every tiny task. Create milestone snapshots only at meaningful verified gates.

## Two gates per milestone

### Delivery gate

Require project evidence such as:
- target tests pass;
- integration behavior is observed;
- known failure path is exercised;
- required docs/config match reality.

### Mastery gate

Select only the A-class concepts introduced in the milestone and ask the learner to:
- explain the problem and invariant;
- predict one failure;
- locate the relevant implementation/test;
- make or describe one safe modification.

A milestone may be delivered before full interview-level mastery. Record the gap honestly.

## Rollback mental model

If history is:

`M0 → M1 → M2 → M3`

and M1 is later found wrong:
- preserve M2/M3 snapshot refs;
- repair from the last trusted point using a `fix/...` line or an explicit history strategy;
- migrate/replay later changes deliberately;
- do not destroy later refs just to make history look clean.

Teach the learner that “branch still exists” and “branch is based on corrected history” are different questions.

## Learning note at milestone creation

Record:
- milestone branch/tag;
- exact verified behavior;
- A-class concepts introduced;
- tests/evidence;
- unresolved learning gaps.

This makes later interview revision tied to real code rather than memory.
