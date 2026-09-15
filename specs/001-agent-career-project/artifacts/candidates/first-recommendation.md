# First Recommendation — Historical Record

> **Status: SUPERSEDED**
>
> This file preserves the first recommendation produced at the end of the original Contract 2 scoring pass. It is intentionally not the current final project decision. See `../decisions/final-selection.md` for the authoritative selection.

## Original first recommendation

**C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent**

The original scoring/validation phase favored C1 because it provided a compact enterprise workflow with Tool/API execution, structured business state, backend transactions, approval, idempotency and strong evaluation feasibility.

At that point, the principal known risk was already recorded: procurement might become a glorified deterministic rules/workflow system if the Agent judgment boundary was not strong enough.

## Why this recommendation was later superseded

A subsequent P0 business-value challenge made the risk decisive: too much of the project's headline value could be explained by ordinary ERP/workflow automation, while the Agent-specific value was concentrated in requirement clarification and evidence selection.

The decision process was therefore reopened rather than defending the original ranking.

The revised candidate **C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent** provides a stronger combination of:
- recognizable operational pain;
- ambiguous user intent;
- evidence-dependent next-tool decisions across order/logistics/policy systems;
- deterministic Java authority for eligibility, money and state changes;
- naturally meaningful timeout/idempotency/HITL/security cases;
- deterministic offline evaluation.

## Audit value

This file remains in the repository to show that:
1. the first recommendation was not treated as irreversible;
2. red-team/user challenge could change the answer;
3. the current final selection is evidence/argument driven rather than anchored to an early choice.

**Current authoritative recommendation: CommerceAgent — E-commerce After-sales Execution & Exception Handling Agent.**
