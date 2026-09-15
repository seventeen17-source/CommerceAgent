# ProcurePilot 6+2 Week Roadmap

Core budget: **6 weeks / roughly 90–150 focused hours**. Weeks 7–8 are buffer/polish and never required for the core demo.

## Week 1 — Domain, tool and eval contracts

### Runnable deliverable
- Java business backend skeleton with persistent supplier/quote/budget/request fixtures and one read API/tool contract.
- Agent service can call one typed read tool against the local backend.
- 10–15 initial dev eval cases represented in the future implementation's evaluation format.

### Acceptance
- Purchase-request state and authoritative business facts are defined.
- Tool inputs/outputs and permission boundaries match `tool-contracts.md`.
- Agent/deterministic boundary is frozen.
- Must scope is frozen; after Week 2 no new Must items are added.

### Learn / personally understand
- Agent vs deterministic authority.
- HTTP/tool contracts and schema validation.
- relational constraints, transactions and idempotency concept.
- evaluation-case oracle design.

### Risk / cut
If dual-service setup is too expensive, simplify framework/UI first; do not remove persistent business state or eval format.

## Week 2 — First vertical slice

### Runnable deliverable
Normal path:
`user request → Agent → supplier/quote/budget tools → create_purchase_request → verified result`.

Controlled failure path:
- missing blocking requirement **or** budget/policy block causes clarification/safe stop without write.

### Acceptance
- Real end-to-end `User → Agent → Tool → Business System → Result` works.
- One effective idempotent write.
- Same run has structured trace with tool args/results and final business state.
- No real ERP/SaaS dependency.

### Learn / personally understand
- explicit state graph;
- conditional routing;
- model structured output/tool choice;
- write preconditions and state verification.

### Circuit breaker
If Week 2 slice is not working, delete UI polish, RAG sophistication and MCP before extending the deadline.

## Week 3 — Reliability, safety and HITL

### Runnable deliverable
Demonstrate:
- tool timeout + bounded retry;
- stale quote or invalid parameter;
- duplicate request/idempotency;
- unauthorized/high-risk write blocked;
- Human-in-the-loop approval pause/resume;
- Prompt Injection in untrusted supplier/policy text;
- unknown write outcome followed by status verification.

### Acceptance
- unsafe effective writes = 0 in the Week-3 safety cases.
- write retries use the same idempotency key and verify ambiguous outcomes.
- requester cannot self-approve.
- retrieved content cannot alter permissions.

### Learn / personally understand
- retry semantics;
- at-least-once request risk and idempotency;
- approval/checkpoint state;
- injection threat model and least privilege.

### Cut
Second business scenario, external APIs, Multi-Agent, queue/cache/K8s remain cut.

## Week 4 — Freeze evaluation and run Baseline vs V1

### Runnable deliverable
- complete 60-case dataset version;
- frozen test split;
- deterministic scorers;
- Baseline and V1 run under same model/tool/budget conditions;
- failure taxonomy report.

### Acceptance
- dataset version/hash recorded;
- test answers are frozen before optimization;
- required metrics compute with explicit denominators;
- every failed case has a failure category;
- p50/p95 latency includes retries.

### Learn / personally understand
- eval validity and leakage;
- deterministic vs model judges;
- error analysis;
- experiment comparability.

### Cut
Do not add new features because a metric looks weak. First classify failures.

## Week 5 — One attributable optimization

### Runnable deliverable
Choose the largest high-value dev-set failure class and make **one** focused change, for example:
- missing-field decision policy;
- tool schema/routing;
- retrieval fusion/reranking;
- stale-evidence validation.

Rerun Baseline/V1/Optimized under comparable conditions and check regressions, cost and latency.

### Acceptance
- the changed mechanism has a clear causal hypothesis;
- same evaluation conditions are used or incompatibility is disclosed;
- gains in one metric do not silently create safety/policy regressions;
- no cherry-picked run is reported.

### Learn / personally understand
- data-driven iteration rather than prompt guessing;
- tradeoffs among success, calls, latency and cost.

## Week 6 — Reproducible core and evidence ledger

### Runnable deliverable
- Docker Compose local stack on a clean environment;
- happy path plus at least two failure/safety demo paths;
- stable run trace and eval report;
- architecture and limitation documentation;
- raw evidence required for future resume claims.

### Acceptance
- another developer can start the core from documented steps;
- no core feature depends on Week 7/8 work;
- selected metrics are reproducible from raw run artifacts;
- synthetic/local enterprise boundary is clearly disclosed.

### Learn / personally understand
- full-system debugging;
- reproducibility;
- explaining architecture tradeoffs under interview questioning.

## Week 7 — Optional depth / buffer

Choose at most one after Week 6 PASS:
- MCP adapter for the existing tool contracts;
- deeper adversarial/failure injection;
- one low-risk real external adapter;
- hybrid retrieval improvement justified by eval.

Do not start a second procurement suite or Multi-Agent architecture.

## Week 8 — Recruiting package and rehearsal

Optional polish:
- README cleanup and architecture diagram;
- 60–90 second demo recording;
- Chinese resume bullets populated only with approved measured claims;
- interview whiteboard/reimplementation practice;
- final evidence audit.

## Scope protection rules

1. Week 1 freezes Must.
2. After Week 2, no new Must without deleting an equal-or-larger scope item.
3. Delay causes deletion in this order: decorative UI → external adapter → MCP → second scenario/depth → retrieval sophistication.
4. Never delete core business-state change, Agent dynamic decision, failure handling, safety, evaluation or trace to make the schedule look green.
