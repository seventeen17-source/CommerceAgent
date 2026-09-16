# Session Workflow

## Goal

Turn one repository task into one learnable, verifiable increment. Do not convert every session into a full course.

## 1. Anchor on a real outcome

Start with one behavior such as:
- “POST /refunds is idempotent under duplicate submission.”
- “A LangGraph run can resume after WAITING_USER.”
- “Python runtime credentials cannot read the commerce schema.”

Avoid vague goals like “learn PostgreSQL” or “learn LangGraph” when a project task is available.

## 2. Establish the current state

Inspect only what is needed:
- relevant task/spec;
- target files;
- current test/error;
- existing interfaces and conventions.

State what is already present versus what will be created. Never teach from an imagined repository state.

## 3. Identify one failure story

A mechanism becomes memorable when attached to a failure.

Examples:
- idempotency: response times out after DB commit, client retries;
- checkpoint: process dies while waiting for user input;
- auth boundary: model supplies someone else's order ID;
- transaction: operation record commits but refund row does not;
- eval: a final answer sounds right while DB state is wrong.

Ask: “What happens today?” before introducing the solution.

## 4. Teach the minimum mental model

Explain:
- actors/components;
- source of truth;
- state transition;
- invariant;
- failure/recovery path.

Use a short ASCII flow if it reduces ambiguity.

## 5. Decide whether to isolate the concept

Use a tiny experiment when the full project has too many moving parts.

Good tiny experiments:
- one FastAPI endpoint with Pydantic validation;
- two concurrent inserts against a UNIQUE constraint;
- a LangGraph interrupt/resume with an in-memory tool double;
- one tool call with intentionally invalid arguments.

Skip the toy experiment if the production slice is already small enough to observe directly.

## 6. Integrate with the real project

Name the actual files/interfaces. Explain how the new mechanism changes the end-to-end flow.

Prefer vertical slices over layer dumps. For example, implement enough API + tool + graph + test to prove one refund flow before generating every entity in the system.

## 7. Require learner ownership

Pick one task that is small but semantically important:
- add one validation condition;
- choose the safe retry behavior;
- finish one branch of a state transition;
- write one assertion;
- explain which component should own a decision.

Avoid fake participation such as asking the learner to rename a variable after the tutor wrote everything important.

## 8. Inject or simulate failure

At least once in a substantial A-class section, break the happy path intentionally.

Examples:
- duplicate request;
- invalid JWT;
- timeout after commit;
- stale approval;
- process restart;
- malformed tool args;
- policy lookup missing;
- conflicting order state.

Ask the learner to predict the observable result before revealing it when the help level permits.

## 9. Verify

Use the strongest feasible evidence:
1. deterministic automated test;
2. integration test / authoritative DB or API state;
3. trace/log with specific assertion;
4. manual UI observation only when no stronger mechanism applies.

Never mark a mechanism understood because the code compiles.

## 10. Teach-back and stop

Ask 2–4 questions, selected from:
- What problem did we solve?
- Who owns the decision?
- What is the source of truth?
- What happens if the request is duplicated?
- What happens if the process dies here?
- Which test proves the invariant?
- Why not use the simpler alternative?

If the learner cannot answer, diagnose the exact gap and give one targeted micro-exercise. Do not restart the whole lesson.

## Session size

A normal section should be finishable in one focused sitting. If a task contains more than two new A-class concepts, split it at an observable boundary.

Examples:
- JWT verification and owner authorization can be separate sections.
- checkpoint basics and post-write recovery should usually be separate sections.
- baseline interface and statistical evaluation should not be introduced in the same first session.
