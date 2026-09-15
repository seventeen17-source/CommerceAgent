# Candidate Fatal Gates — Final Decision

The historical candidate set was useful for comparison, but only the current selected candidate matters for the implementation handoff.

## C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent

| Gate | Verdict | Reason |
|---|---|---|
| Two-week vertical slice | PASS | A local order/logistics/eligibility/refund stack can demonstrate a happy path and controlled failure by Week 2 |
| No inaccessible core dependency | PASS | Synthetic/local business systems are sufficient; no production e-commerce or payment credentials are required |
| Genuine Agent judgment | PASS with hard condition | Ambiguous intent, order resolution and evidence-dependent next-tool/path choice must be demonstrated |
| Offline eval feasible | PASS | Resettable order/logistics/policy state supports deterministic tool/action/final-state oracles |
| Reliability/security/observability in 8 weeks | PASS | Scope is restricted to after-sales; idempotency, auth, HITL, timeout recovery and trace are core |
| 60-second business value | PASS | “Not tell the user how to refund; diagnose the case and safely execute or escalate the after-sales process” |

## Fatal condition

If implementation collapses into `intent → fixed refund API`, **Genuine Agent judgment = FAIL** and the project must be redesigned before any optional technology is added.

## Rejected alternatives

- C1 Procurement: rejected as primary project because too much headline value can be implemented as deterministic ERP/workflow logic.
- C2 DevOps/R&D Incident: technically strong but overlaps materially with the existing OpsPilot_Agent portfolio direction.
- C3 Data/BI: credible but risks looking like Text-to-SQL unless action depth is unusually strong.
- C4 Internal Workflow: feasible but less differentiated.
- C5 Financial Operations: strong hiring evidence but higher domain/safety explanation burden for this project budget.

**Final fatal-gate outcome: CommerceAgent PASS; implementation handoff authorized.**