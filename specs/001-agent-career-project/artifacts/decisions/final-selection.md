# Final Project Selection

## Selected candidate

**C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent**

Status: **SELECTED after Contract 3 red-team review**.

This selection is frozen for the remainder of `001-agent-career-project` unless a stated revisit trigger is hit. It does not authorize application code in this feature; it authorizes the A–Q design phase.

## Why selected

C1 survives all six fatal gates, the close-ranking bounded validation, and three independent red-team reviews. Its strongest advantage is not that procurement is the most common Agent job title; it is that procurement provides a compact enterprise task where the portfolio can demonstrate the capabilities most consistently supported by the market evidence:

- ambiguous task interpretation;
- stateful multi-step workflow;
- Tool/API execution;
- structured business-system state;
- RAG for non-structured policy knowledge only;
- approval and safe writes;
- idempotency and failure recovery;
- offline evaluation and run tracing.

It also adds more portfolio diversity than C2 because the user already has an OpsPilot-style incident/operations Agent direction.

## Explicit positioning

Do **not** present the project as evidence that “procurement Agent is the hottest hiring direction.”

Present it as:

> an enterprise execution Agent that converts an incomplete purchase request into a policy-checked, budget-aware, supplier-comparable, approval-ready business transaction while keeping deterministic business rules and risky writes outside model authority.

## Scope frozen as core

- One procurement category/domain.
- One requester-to-approval/PO-draft workflow.
- Persistent supplier, quotation, budget, purchase-request, approval and audit state.
- Several read tools plus controlled idempotent writes.
- Dynamic Agent decisions for missing information, evidence/tool selection, constrained comparison and escalation.
- Server-side validation for price/budget/policy/permissions/state transitions.
- Policy retrieval with citations if retrieval adds value.
- Human approval for high-risk writes.
- Versioned offline eval set and reconstructable trace.
- Failure scenarios: timeout, invalid tool/parameter, stale quote, duplicate call, prompt injection, unauthorized write, partial failure.

## Deleted / downgraded after red team

### Reject from core
- Multi-Agent unless a measured single-Agent limitation appears.
- Kubernetes.
- Message queue/event infrastructure.
- Redis/cache unless a measured bottleneck appears.
- Broad supplier lifecycle/contract/logistics/inventory suite.
- Recommendation-model training, SFT/RLHF.
- Multiple real SaaS/ERP integrations.
- Decorative admin dashboard.

### Should, not Must
- MCP adapter after simple tool contracts work.
- One real external adapter if authentication/data access is easy and does not become a dependency.
- Minimal web UI for task progress/approval.
- Cloud deployment after local reproducibility.

## Strongest rejected alternatives

### C2 DevOps/R&D Incident Agent
Technically excellent and directly aligned with AI backend/platform/R&D-efficiency hiring. Rejected here primarily because of portfolio overlap with the user's existing OpsPilot_Agent direction and higher infrastructure-sprawl risk. Revisit if OpsPilot is abandoned or not used for recruiting.

### C5 Financial Operations / Policy Compliance Agent
Strongest direct domain-specific hiring evidence in the strict sample. Rejected because the finance/safety communication burden is higher, the user's background fit is weaker, and procurement offers a cleaner general-enterprise explanation without sacrificing Tool/safety/eval depth.

## Residual risks

1. **Agent necessity risk**: if implementation turns into a fixed linear form workflow, C1 loses its main justification.
2. **Hiring specificity risk**: procurement itself is not a universally named target role; hiring narrative must remain capability- and enterprise-execution-oriented.
3. **Synthetic-system risk**: local business data must be stateful and contract-realistic rather than a stateless mock.
4. **Evaluation risk**: supplier choice cannot be judged solely by one “correct” answer; deterministic constraints and acceptable-choice predicates are required.

## Revisit triggers

Reopen selection if any of the following occurs during A–Q design or later implementation:
- fewer than three independently testable scenarios require genuinely dynamic next-action/tool/evidence choice;
- the Week-2 vertical slice cannot be implemented without real ERP/vendor credentials;
- reliable evaluation requires subjective manual grading for most cases;
- persistent business-state/idempotency requirements expand beyond the six-week core;
- the user decides not to use OpsPilot for recruiting, materially increasing C2 portfolio value.

## Contract 3 verdict

- Three independent red-team memos: PASS.
- Every identified issue has a disposition: PASS.
- No unresolved P0 at design stage: PASS, with Agent-necessity implementation gate preserved.
- Alternatives compared and switch allowed: PASS.
- Recommendation consistent with evidence, constraints and existing portfolio: PASS.

**Contract 3: PASS. Proceed to A–Q final project specification.**
