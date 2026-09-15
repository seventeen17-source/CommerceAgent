# Red Team — Developer Elimination Memo

Target: C1 Procurement & Supplier Execution Agent. Alternatives: C2 DevOps/R&D Incident, C5 Financial Operations.

| issue_id | severity | challenge | evidence / failure scenario | proposed disposition |
|---|---|---|---|---|
| DEV-01 | P1 | Synthetic supplier/quote data may make the engineering too easy | If tools are only dictionary lookups, there is little real backend/state complexity | **strengthen deterministic system, not breadth**: persistent relational state, quote validity windows, budget reservations, request state machine, audit and idempotent writes |
| DEV-02 | P1 | Recommendation can become non-deterministic and hard to debug | Multiple acceptable suppliers; an LLM can rationalize arbitrary choices | **constraint-first design**: deterministic eligibility/price/deadline facts; Agent chooses evidence and explains tradeoffs; eval uses predicates rather than exact supplier text |
| DEV-03 | P1 | Tool failure and partial writes can corrupt state | timeout after a write, repeated retry, stale quote, duplicate request | **Must**: idempotency keys, write verification, bounded retry only for safe reads/idempotent calls, explicit partial-failure state |
| DEV-04 | P1 | Policy/RAG text can carry prompt injection or stale instructions | malicious supplier note or retrieved document tells the Agent to bypass checks | **Must**: retrieved text is untrusted data; server-side permission/policy validation; source/version metadata; no prompt can grant write permission |
| DEV-05 | P2 | Real supplier/ERP adapters will consume the schedule | auth, rate limits, vendor-specific schemas and data licenses add little evidence | **delete from core**; local contract-realistic adapter first, external adapter only Should |
| DEV-06 | P2 | Multi-Agent/MCP/queue/cache can create unnecessary failure modes | components would be added because they are popular rather than required | **reject Multi-Agent/queue/cache/K8s in core; MCP Should only after base tools work** |
| DEV-07 | P1 | C2 may actually be easier to defend technically if infrastructure is simulated | seeded incidents have crisp ground truth and diagnosis/remediation oracles | **compare C2 after scope cut**: service simulator, logs/deploy history, 5–6 tools, one safe remediation; no real K8s required |

## Developer verdict

C1 is technically feasible and safer than C5, but its strongest engineering evidence comes from reliability/state/evaluation rather than procurement complexity itself. C2 has a potentially cleaner causal evaluation story (seed fault → evidence → diagnosis → remediation → health verification) if infrastructure is kept local and deterministic. This is strong enough to justify re-scoring rather than automatically retaining C1.
