# CommerceAgent Scope Cut Plan

## Must
- one after-sales domain: refund / return / logistics anomaly / escalation;
- one primary user flow plus meaningful evidence-dependent branches;
- explicit Agent state graph;
- Tool contracts and validated parameters;
- Java authoritative order/eligibility/write backend;
- idempotent write handling;
- one high-risk Human-in-the-loop path;
- Prompt Injection and authorization defense;
- policy retrieval only where unstructured knowledge is needed;
- 60–80 case offline evaluation;
- per-run trace and error taxonomy;
- reproducible local startup.

## Should
- MCP adapter over existing HTTP tool contracts;
- second after-sales sub-scenario using the same core;
- fault injection automation;
- simple approval UI;
- basic trace visualization;
- Docker Compose.

## Nice
- richer frontend;
- advanced retrieval/reranking;
- cloud deployment;
- more policy categories;
- more business dashboards.

## Reject for core
- broad pre-sales/customer-service platform;
- product recommendation;
- ads/merchant operations;
- procurement module;
- real payment provider integration;
- full RBAC admin platform;
- Kafka/event architecture without measured need;
- Redis without measured need;
- Kubernetes;
- Multi-Agent;
- fine-tuning/RLHF.

## Freeze rules
- Week 1: freeze Must scope.
- After Week 2: no new Must unless a current Must cannot be made correct/safe without it.
- New technology may enter only by replacing complexity, not simply adding to it.

## Circuit breakers

### If Week 2 vertical slice fails
Cut frontend/policy-RAG complexity and prove `User → Agent → Tool → Backend → safe write/no-write → verification` first. If evidence-dependent Agent branching still cannot be demonstrated, reopen project selection.

### If Python learning curve delays progress
Keep Agent graph minimal and explicit; avoid framework-specific abstractions. Do not move deterministic rules into prompts to compensate.

### If retrieval quality is poor
Use a smaller versioned policy corpus or deterministic document lookup. RAG is not allowed to block the core after-sales execution path.

### If model cost/availability is unstable
Keep eval data and backend deterministic; support a lower-cost model/config for development. Report actual configuration in results.

### If frontend delays progress
Replace with minimal chat/approval UI or CLI. Do not cut safe writes, eval or trace.

## Cut order when behind schedule
1. visual polish;
2. MCP;
3. second scenario breadth;
4. cloud deploy;
5. advanced RAG;
6. observability UI.

Never cut before core completion:
- deterministic Agent/backend boundary;
- dynamic next-tool/evidence branch;
- authorization;
- idempotency;
- HITL;
- eval;
- trace.
