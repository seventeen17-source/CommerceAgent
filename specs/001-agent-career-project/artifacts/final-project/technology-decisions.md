# ProcurePilot Technology Decisions

These decisions are allowed only because Contract 3 has passed. They are implementation recommendations for the future implementation feature, not application code in this feature.

| Technology / capability | Enterprise value | Project necessity | 2-month learning ROI | Complexity cost | Priority | Decision / revisit trigger |
|---|---|---|---|---|---|---|
| Java + Spring Boot business backend | Strong fit for transactional enterprise services, validation, state machines, audit and APIs | Gives the Agent a real deterministic business system instead of in-memory mocks | High: leverages existing strength and demonstrates mainstream backend engineering beside AI | One service, persistence, transactions, tests | **Must** | Use for supplier/quote/budget/request/approval/PO domain logic. Revisit only if scope proves a separate backend adds no real domain logic |
| Python Agent service | Dominant ecosystem for LLM/Agent experimentation, eval tooling and model SDKs | Separates probabilistic orchestration from deterministic business authority; not required for business truth | High because Python/Agent engineering is a stated skill gap and appears across target jobs | Cross-language API boundary and deployment | **Must** | Keep the boundary narrow: Agent orchestration/eval only. Revisit if Week-1 spike shows one-language implementation materially reduces risk without losing learning goals |
| LangGraph or equivalent explicit state graph | Provides inspectable state, conditional routing, checkpoints and bounded tool loops | Strongly matches the project's need for missing-info branches, checks, approval pause and failure paths | High: teaches stateful Agent engineering rather than a chat loop | Framework concepts and version churn | **Must capability; framework replaceable** | Prefer LangGraph if stable at implementation time; otherwise implement equivalent explicit state machine. The capability is Must, the vendor/framework is not |
| OpenAI-compatible model API abstraction | Allows model experimentation without coupling business rules to one vendor | A model is needed for intent/decision/comparison tasks | High | Model variability, cost and rate limits | **Must capability** | Provider remains configurable; no multi-provider abstraction beyond a small interface unless needed |
| Minimal web UI | Makes task progress, clarification, approval and trace visible | Useful for demo/HITL but not needed for core Agent correctness | Medium | Frontend time | **Should** | Use a small React/Vite or similarly simple UI. If delayed, a minimal internal page/API client is acceptable |
| MCP adapter | Standardized interoperability appears in target roles and can expose tools consistently | Base project can work with ordinary HTTP/tool functions; MCP does not create business value by itself | Medium/high once the base system works | Extra protocol/runtime concepts | **Should** | Add after HTTP/tool contracts and eval are stable. Never make Week-2 slice depend on it |
| RAG for procurement policy | Grounds non-structured policy/approval/category knowledge with citations | Needed only for policy text that cannot be represented as simple authoritative fields/rules | High, because retrieval is common in target roles and creates injection/citation test cases | Chunking/index/retrieval/eval | **Must for a small policy corpus** | Keep structured facts in DB/APIs. If policy corpus is tiny, a simple retrieval implementation is sufficient |
| PostgreSQL | Transactional persistent state, relational constraints and audit-friendly queries | Needed to make budget/request/approval/idempotency behavior contract-realistic | High and familiar enterprise choice | Schema/migrations | **Must** | One database for business state; avoid database proliferation |
| pgvector / vector search | Supports semantic policy retrieval inside existing DB | Not required if policy corpus can be served by simpler retrieval; useful to demonstrate embeddings without another service | Medium | Extension/index tuning | **Should** | Prefer same Postgres if used. Revisit based on policy retrieval eval; do not add a separate vector DB by default |
| Hybrid lexical + semantic retrieval | Better robustness for policy IDs, thresholds and domain terms | Valuable if semantic-only retrieval misses exact terms | Medium | Fusion/ranking code | **Should** | Add only if baseline retrieval error analysis justifies it |
| Structured run/tool audit tables | Reconstruct one Agent run without relying on a vendor dashboard | Directly required by spec and market evidence | High | Schema and logging discipline | **Must** | Store run, step, model usage, tool execution, retrieval refs, errors, approvals and outcome |
| Langfuse/LangSmith or hosted tracing | Convenient visualization and eval integration | Not required if local trace/eval artifacts are complete | Medium | External service/config/cost | **Nice** | Use only if setup is trivial and data policy is acceptable |
| Docker Compose | Reproducible local multi-service demo | Makes Java/Python/Postgres setup repeatable for reviewers | High | Small packaging cost | **Must** | One-command local stack by Week 6 |
| Cloud deployment | Improves demo accessibility | Not necessary for correctness/interview evidence | Medium | Credentials/cost/ops | **Should** | Add only after reproducible local core |
| GitHub Actions CI | Reproducible tests and contract/eval smoke checks | Helpful but not part of Agent logic | Medium | Workflow maintenance | **Should** | Add after stable test commands |
| Redis/cache | Useful at scale | No measured bottleneck or distributed-session need in core | Low | New state/failure mode | **Reject core** | Revisit only after measured latency/throughput need |
| Kafka/message queue/event bus | Useful for large asynchronous workflows | Not required for one bounded procurement flow | Low | Significant operational complexity | **Reject** | Do not add for architecture decoration |
| Kubernetes | Enterprise orchestration at scale | No two-month project necessity; Docker Compose proves reproducibility | Low for this project's hiring signal relative to cost | Cluster/ops overhead | **Reject** | Learn conceptually if targeting platform roles, not implement here |
| Multi-Agent | Can divide specialist roles in complex systems | One explicit state graph can solve current workflow and is easier to evaluate | Low/negative before evidence | Coordination, state, eval and debugging complexity | **Reject by default** | Revisit only if measured single-Agent/state-graph limitation appears |
| Long-term user memory | May personalize recurring procurement | No current business requirement | Low | Privacy/state/quality burden | **Reject** | Session/task state only |
| SFT/RLHF/Agentic RL | Can optimize model behavior at scale | Core failures are expected to be workflow/tool/eval problems, not training problems | Low for current target | Data/GPU/experimentation complexity | **Reject** | Revisit only after implementation evidence shows prompt/workflow/tool changes cannot solve a high-value failure class |

## Architecture decision

Recommended future implementation boundary:

```text
Minimal Web UI
    |
    v
Python Agent Service
(explicit state graph, model calls, tool orchestration, eval hooks)
    |
    | typed HTTP tool calls first; optional MCP adapter later
    v
Java Spring Boot Business Backend
(authoritative validation, transactions, permissions, idempotency, state machine)
    |
    v
PostgreSQL
(business state + audit; optional pgvector for policy retrieval)
```

This split is not justified by “show two languages.” It is justified only if the Java service owns meaningful deterministic business semantics and the Python service owns probabilistic Agent orchestration/evaluation. If later implementation collapses either side into an empty wrapper, the split must be simplified.
