# CommerceAgent Technology Decisions

The selected project is an e-commerce after-sales execution and exception-handling Agent. Technology is justified by business responsibility, not by keyword popularity.

| Technology / capability | Enterprise value | Project necessity | 2-month learning ROI | Complexity cost | Priority | Revisit trigger |
|---|---|---|---|---|---|---|
| Java + Spring Boot | Deterministic business APIs, transactions, permissions and state safety | Own order/after-sales domain, eligibility, idempotent writes, audit | High; aligns with backend interviews and user's strength | Medium | **Must** | Revisit only if implementation is intentionally single-language and can preserve equal backend depth |
| Python + FastAPI | Fast model/Agent ecosystem and eval integration | Agent orchestration and eval runner | High; fills user's weaker Python Agent engineering area | Medium | **Must** | Could collapse into Java only if Python split becomes empty ceremony |
| Explicit state graph | Bounded, auditable long-running task orchestration | Dynamic evidence gathering, retry/approval/write/verify flow | Very high | Medium | **Must** | Reject graph framework if simple explicit state machine provides same clarity |
| PostgreSQL | Transactional authoritative business state | Orders, after-sales writes, approvals, audit, eval reset state | High | Low/medium | **Must** | None for core unless a simpler relational DB is required by environment |
| Tool/API Calling | Connect Agent to real business capabilities | Central to project value | Very high | Medium | **Must** | None; without tools project becomes chatbot |
| RAG for policy/SOP | Retrieve unstructured policy with citations | Useful for explanation and policy context, but not business authority | High | Medium | **Should** | Cut if policy corpus is too small; use direct versioned lookup instead |
| MCP | Standardized tool protocol and good interview topic | Not needed to prove business flow; HTTP tools suffice for MVP | Medium/high | Medium | **Should** after MVP | Add in Week 7 if core is stable and it demonstrates protocol portability |
| React/simple frontend | Makes demo and HITL visible | Useful but not core intelligence | Medium | Medium | **Should** | Replace with minimal HTML/CLI if frontend threatens core schedule |
| Docker Compose | Reproducible multi-service demo | Helps reviewers run Java/Python/Postgres stack | High | Low | **Should** | Use plain processes if container setup becomes disproportionate |
| Observability / structured tracing | Debugging, reliability and interview evidence | Required to reconstruct an Agent run | Very high | Medium | **Must** | Implementation library may vary; capability may not be cut |
| Offline Eval harness | Measures task/tool/state/safety behavior | Required to prove Agent adds value over baseline | Very high | Medium | **Must** | None |
| Human-in-the-loop | Prevent autonomous high-risk writes | Required for high-value/exception cases | High | Low/medium | **Must** for one path | Threshold/policy can be simplified, capability retained |
| Redis | Cache/session optimization | No demonstrated need in core | Low | Medium | **Reject core** | Add only after measured latency/state-sharing need |
| Kafka/message queue | Async scale/event workflows | Core demo does not require production-scale eventing | Low | High | **Reject core** | Add only for a specific async business requirement |
| Kubernetes | Production orchestration | Does not improve core proof in 8 weeks | Low | High | **Reject** | Only after core project complete, never MVP |
| Multi-Agent | Specialized role decomposition | No evidence it beats one explicit after-sales state graph | Low | High | **Reject core** | Revisit only if a measured task family truly needs independent agents |
| Fine-tuning/RLHF | Model behavior specialization | Not needed for the project thesis | Low | Very high | **Reject** | Only future research with data and clear measured need |
| Vector DB as mandatory platform | Scalable retrieval | Policy corpus may be small enough for simple retrieval | Medium | Medium | **Nice / conditional** | Adopt only if corpus/eval justifies it |

## Architectural choice

Recommended baseline:

```text
Simple Web UI
   ↓
Python Agent Service (FastAPI + explicit state graph)
   ↓ Tool contracts over HTTP
Java After-sales Backend (Spring Boot)
   ↓
PostgreSQL

Policy retrieval + Trace/Eval are supporting capabilities.
```

## Critical decision: RAG is not refund authority

A policy chunk may say “物流异常可申请退款”, but the Agent cannot convert that sentence directly into a money-changing authorization.

The authoritative path is:

`policy evidence (optional) + order/logistics state → Java eligibility service → allowed action/max amount/approval requirement → Agent chooses next business path → guarded write`

This separation is a Must because it is both a real enterprise safety pattern and a strong interview design point.

## Critical decision: Java/Python split must earn its existence

Java exists for substantial domain logic, not résumé decoration. Python exists for actual Agent orchestration/eval, not merely proxying requests. If either side becomes a shell, collapse the split rather than preserve empty complexity.
