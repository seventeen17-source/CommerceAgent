# CommerceAgent 6+2 Week Roadmap

Core duration: 6 weeks. Weeks 7–8 are buffer/depth/packaging, never dependencies for the core demo.

## Week 1 — Business domain, contracts and eval skeleton

### Runnable deliverable
Java backend exposes synthetic but contract-realistic order/logistics/eligibility APIs; Python service can call one read tool.

### Build
- domain entities: User, Order, OrderItem, Shipment, RefundRequest, ReturnRequest, SupportTicket, ApprovalRequest, AuditLog;
- deterministic order ownership and after-sales eligibility rules;
- tool schemas for `get_order`, `get_logistics`, `check_after_sales_eligibility`;
- initial 10–15 eval cases covering refund, return, ambiguous order and denial.

### Must understand/reproduce
- Spring transaction/state boundaries;
- Tool schema validation;
- why eligibility belongs in backend rather than prompt/RAG.

### Exit gate
Business outcome, Agent/backend boundary, tool contracts, eval case schema and scope-cut rules are frozen.

## Week 2 — First vertical slice

### Runnable deliverable
One normal logistics-anomaly refund and one controlled failure complete:

`User → Agent → Tool → Java Business System → Write/No-write → Verification → Result + Trace`

### Build
- explicit Agent state graph;
- order resolution;
- dynamic choice to inspect logistics;
- deterministic eligibility call;
- idempotent refund request;
- post-write verification;
- trace for the whole run.

### Controlled failure
Use ambiguous order or unavailable logistics; Agent must clarify/escalate without unsafe write.

### Exit gate
If Week 2 cannot demonstrate evidence-dependent branching, stop feature growth and fix Agent necessity before continuing.

## Week 3 — Reliability, safety and HITL

### Runnable deliverable
Demonstrate:
- read timeout + bounded retry;
- refund-write timeout + idempotency/status recovery;
- wrong tool/parameter prevention;
- Prompt Injection attempt;
- cross-user order access denial;
- high-value refund entering `WAITING_APPROVAL`;
- return path for delivered goods.

### Must understand/reproduce
- idempotency-key semantics;
- ambiguous completion recovery;
- server-side auth/permission checks;
- Human-in-the-loop state/resume.

## Week 4 — Freeze 60–80 case evaluation

### Runnable deliverable
Versioned dataset and Baseline vs V1 results on identical conditions.

### Build
- target 74 cases;
- dev/test split;
- resettable backend fixtures;
- deterministic scorers for tool/parameter/state/unsafe/duplicate-write;
- retrieval/citation scorer for policy cases;
- error taxonomy dashboard/table.

### Exit gate
No manual cherry-picking; test answers remain frozen during optimization.

## Week 5 — One attributable optimization

### Runnable deliverable
Identify the largest V1 error category and make exactly one focused improvement.

Examples:
- better order disambiguation;
- better evidence-sufficiency state transition;
- better tool-selection context;
- better policy retrieval version filtering.

Rerun the same evaluation and report regressions, latency and token change alongside success metrics.

## Week 6 — Reproducible core and evidence package

### Runnable deliverable
Fresh-environment startup and complete demo with:
- normal refund;
- return path;
- failure recovery;
- Prompt Injection/authorization defense;
- HITL;
- trace;
- eval report.

### Evidence package
- architecture diagram;
- actual measured eval report;
- known limitations;
- reproducible quickstart;
- resume claim ledger linking any number to run/dataset/metric.

## Week 7 — Optional depth

Choose at most one:
- add MCP adapter over the same tool contracts;
- add a second after-sales subdomain using the same core;
- deeper fault/adversarial testing;
- stronger observability visualization.

Do not add Multi-Agent/Kubernetes merely for keywords.

## Week 8 — Packaging and interview replay

- README polish;
- 60–90 second demo video;
- interviewer question rehearsal;
- manually reimplement simplified state graph, idempotent write and eval scorer without relying on generated code;
- final evidence/metric audit.

## Scope cut order

If delayed, cut in this order:
1. polished frontend;
2. MCP;
3. second after-sales sub-scenario;
4. cloud deployment;
5. advanced retrieval/reranking;
6. observability UI.

Do **not** cut:
- Agent-vs-deterministic boundary;
- dynamic evidence/tool branch;
- idempotent safe write;
- permission/Prompt Injection defense;
- one HITL path;
- evaluation;
- per-run trace.

## Time budget

Assume roughly 15–25 hours/week. The plan intentionally favors one deep after-sales workflow over a broad “all-in-one customer-service platform”.
