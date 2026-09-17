# A/B Learning Classification

Classify before spending teaching time.

## A-class — must understand

A task is A-class if misunderstanding it could make the learner unable to defend the architecture, debug serious failures, or modify the system safely.

Common A-class areas:
- authorization and trust boundaries;
- transactions and business invariants;
- idempotency and duplicate-write protection;
- concurrency and race conditions;
- timeout ambiguity and recovery;
- workflow state, checkpoint, interrupt, resume;
- model/tool responsibility boundaries;
- structured tool calling and argument validation;
- HITL/approval semantics;
- failure budgets, retry policy, no-progress detection;
- evaluation design and honest baselines;
- state ownership and source of truth;
- data model constraints that enforce correctness;
- important performance/security tradeoffs;
- project-specific architectural decisions.

For A-class work, require at least one of:
- learner predicts behavior;
- learner modifies a meaningful rule;
- learner writes/fixes a focused test;
- learner explains a failure trace;
- learner compares two designs and chooses one with reasons.

Then verify the mechanism with observable evidence.

## B-class — AI may accelerate

B-class work is mostly mechanical and has low independent learning return for the current goal.

Common examples:
- repetitive DTO/entity getters and mappings;
- conventional CRUD repositories with no special invariant;
- basic CSS/layout polish;
- fixtures and seed data;
- repetitive API schema translation;
- simple file moves/renames;
- dependency boilerplate already understood;
- routine Docker wiring after the learner understands the architecture;
- repeated variants of a test whose mechanism is already mastered.

For B-class work, provide a two-part explanation:
1. what role it plays;
2. where to look when it breaks.

Then move on.

## Context can change classification

Examples:
- A DTO is normally B-class, but becomes A-class if it demonstrates why `amount` must not be model-controlled.
- A database migration is normally partly mechanical, but a UNIQUE constraint preventing duplicate refunds is A-class.
- A React component is normally B-class for a backend learner, but state synchronization may be A-class if the current learning goal is frontend concurrency.

## Time allocation guideline

For a learner building an interview project:
- spend roughly 70–80% of explanation/practice time on A-class mechanisms;
- spend roughly 20–30% on B-class orientation and project fluency.

Do not treat this as a rigid clock. It is a bias against wasting learning time on generated boilerplate.
