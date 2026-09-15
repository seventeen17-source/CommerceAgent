# Candidate Evidence Matrix — Final

## Current selected candidate

### C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent

**Core capability evidence from the strict market sample**:
- backend/service engineering;
- Tool/API/Function Calling;
- planning/workflow/state/context;
- RAG/knowledge retrieval where justified;
- evaluation/testing/observability;
- business-system integration;
- reliability/failure handling;
- security/permission/safe writes;
- optional MCP/tool protocol support.

See `../market/capability-signals.csv` and `../market/capability-map.md` for job-level evidence IDs and counts.

**Scenario-specific supporting context**:
Current e-commerce Agent hiring descriptions include intelligent customer service, consumer assistant, logistics/refund and other commerce execution scenarios. These strengthen business-domain plausibility but are not silently added to the strict 30-posting denominator.

**Why this candidate uses the capability evidence well**:
- Tool/API: order, logistics, policy, eligibility, refund/return/ticket/approval/status capabilities.
- Stateful workflow: evidence gathering changes the next action.
- Backend engineering: ownership, eligibility, amount, transaction, state machine and idempotency.
- RAG: policy/SOP only, not structured business truth.
- Eval: resettable cases and deterministic final-state oracles.
- Reliability/security: timeout recovery, duplicate-write prevention, authorization, Prompt Injection and HITL.

## Rejected alternatives

| Candidate | Why not selected |
|---|---|
| Procurement | Agent-specific value too easy to collapse into deterministic ERP/workflow automation |
| DevOps/R&D Incident | Strong technical fit but overlaps existing OpsPilot_Agent portfolio |
| Data/BI | Strong fallback but risks appearing as Text-to-SQL unless action depth is unusually strong |
| Internal Workflow | Feasible but common/generic assistant pattern |
| Financial Operations | Strong demand evidence but greater domain/safety communication burden |

## Evidence discipline

The selected business scenario is a recommendation derived from capability evidence; the repository does not claim that every sampled employer is building this exact product. Hiring facts remain separated from project-design inference.