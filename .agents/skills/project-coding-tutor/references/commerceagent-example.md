# CommerceAgent Example Learning Map

This is an example for a Java-strong learner building a Python/LangGraph after-sales Agent. Adapt it to the repository's actual specs and tasks.

## M0 — Foundation and risk probes

Primary learning targets:
- FastAPI/Pydantic mental model;
- typed LLM tool calling and argument validation;
- PostgreSQL role separation;
- LangGraph checkpoint basics and restart recovery.

Suggested A/B split:
- A: model/tool boundary, checkpoint source of truth, DB permissions.
- B: package scaffolding, routine config, health endpoints.

Java bridges:
- Pydantic model ↔ validated request DTO;
- typed HTTP client ↔ service client/adapter;
- checkpoint ↔ persisted workflow execution state, explicitly *not* a Spring transaction.

Mastery questions:
1. Why can't Python runtime read `commerce` tables directly?
2. What information belongs in graph state, and what must never be persisted there?
3. If the process restarts during WAITING_USER, what identifies the run?
4. Why must invalid tool arguments be rejected outside the model?

## M1 — Refund request end-to-end

Primary learning targets:
- authorization vs semantic intent;
- deterministic eligibility;
- stable operation identity and idempotency;
- write → authoritative verification;
- minimum honest baseline.

Failure drill:
- Java commits the refund request, HTTP response is lost, Python retries.

Mastery questions:
1. Why is “check then insert” alone insufficient under concurrency?
2. Who decides the amount?
3. What does ABSENT from a status query prove—and what does it not prove?
4. Why should the final response say “申请已创建” rather than “退款成功到账”?

## M2 — Return and clarification

Primary learning targets:
- state-dependent tool selection;
- interrupt/resume for missing information;
- user input replay protection;
- honest Agent-value comparison.

Failure drill:
- two candidate orders; user supplies an invalid or other-user order reference.

Mastery questions:
1. When should the Agent ask instead of guess?
2. Which parts of order resolution can be semantic, and which must be authorized deterministically?
3. Why don't four hardcoded branches prove Agent value?

## M3 — Approval and recovery

Primary learning targets:
- human-in-the-loop as a durable state transition;
- approval binding/fingerprint;
- stale approval and expiry;
- concurrent resume and post-write crash recovery.

Failure drill:
- approval is for one amount/order/version, but the order changes before resume.

Mastery questions:
1. Why can the Agent query an approval but not approve it?
2. Why bind approval to action details instead of storing only `approved=true`?
3. What must be re-read before resume?

## M4 — Policy reference and safe stop

Primary learning targets:
- policy text vs executable business rule;
- versioned lookup;
- prompt-injection resistance in retrieved text;
- honest manual fallback.

Failure drill:
- policy text contains instructions telling the model to bypass eligibility.

Mastery questions:
1. Why can policy text explain but not authorize?
2. Why is exact version lookup sufficient for this MVP?
3. What is the correct user-facing statement when automation stops but no support ticket was created?

## M5 — Evaluation and release

Primary learning targets:
- deterministic tests vs real-model behavioral eval;
- dev/test split;
- repeated trials and variance;
- honest fixed-workflow baseline;
- safety attempt vs safety acceptance.

Failure drill:
- Agent answer sounds correct, but authoritative DB state is wrong.

Mastery questions:
1. Why score the environment state instead of only final text?
2. Why can temperature=0 still fail to guarantee identical model outputs?
3. Why report blocked unsafe attempts separately from accepted unsafe writes?
4. What conclusion should you report if the fixed workflow matches or beats the Agent on standard paths?
