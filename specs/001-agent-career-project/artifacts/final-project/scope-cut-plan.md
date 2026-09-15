# ProcurePilot Scope-Cut Plan

## Must freeze

Freeze by end of Week 1:
- one procurement workflow;
- persistent supplier/quote/budget/request/approval/audit state;
- genuine dynamic Agent next-action/tool decisions;
- protected write tools and deterministic business validation;
- idempotency + verify-after-write;
- HITL approval;
- small policy retrieval with citations;
- versioned eval cases and trace.

After Week 2, no new Must may be added without removing an equal-or-larger scope item.

## Cut order when schedule slips

1. Decorative UI / visual polish.
2. Cloud hosting.
3. Real external vendor/ERP adapter.
4. MCP adapter.
5. Hybrid retrieval/reranking sophistication; keep the simplest policy retrieval that meets eval.
6. Additional procurement categories.
7. Optional adversarial depth beyond required security cases.

Do **not** cut:
- state-changing business loop;
- dynamic Agent branch;
- deterministic backend authority;
- timeout/duplicate/unsafe-write handling;
- approval/idempotency;
- evaluation and trace.

## Explicit Reject list

- Multi-Agent without measured single-Agent failure.
- Kubernetes.
- Kafka/event bus.
- Redis/cache without a measured bottleneck.
- microservice decomposition beyond the Agent/business-backend boundary.
- long-term user memory.
- recommendation-model training or SFT/RLHF.
- full supplier lifecycle/contracts/logistics/inventory platform.
- complete RBAC/admin CRUD suite.
- multiple SaaS integrations.

## Circuit breakers

### Week 1
If Java/Python split produces empty wrappers or blocks tool integration, simplify framework/service boundary before adding features.

### Week 2
If end-to-end happy + controlled-failure slice is not working, stop all Should/Nice work and focus exclusively on one persistent request path.

### Week 3
If safe-write/idempotency/approval is unstable, postpone RAG sophistication and UI; do not proceed to more write tools.

### Week 4
If 60-case eval cannot be frozen, reduce category variety while preserving failure/safety coverage; do not fabricate metrics from a hand-picked subset.

### Week 5
If optimization cannot be attributed to one mechanism, report V1 honestly rather than stacking untraceable changes.

### Model/API cost or quota issue
Use a lower-cost compatible model or recorded deterministic fixtures for non-model tests; rerun all compared versions under the same model/config before claiming relative improvement.

## Resume protection

A schedule slip never authorizes turning target metrics into achieved claims. Scope is variable; evidence integrity is not.
