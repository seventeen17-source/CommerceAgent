# Bounded Validation — C1 vs C5 (with C2 fallback)

**Trigger**: Top-1/Top-2 center gap = 0.020 and defensible intervals overlap.

**Validation type**: paper-prototype feasibility validation using explicit tool surfaces, business-state transitions, and 12 deterministic evaluation cases per candidate. The purpose is not to fake an implementation result; it tests whether the candidate can be specified and evaluated without hidden enterprise dependencies.

## C1 Procurement validation

### Minimal deterministic system
Entities: supplier, quote, purchase_request, budget, policy, approval, po_draft.

Minimal tools:
1. `supplier_search`
2. `quote_query`
3. `budget_check`
4. `policy_search`
5. `create_purchase_request`
6. `request_approval`
7. `create_po_draft`

### 12 evaluable cases
1. Complete low-risk request → compare suppliers → create request.
2. Missing delivery date → ask/derive missing constraint before tool execution.
3. Budget insufficient → do not create PO draft.
4. Amount above approval threshold → create approval request, no final write.
5. Supplier not certified → reject candidate supplier.
6. Cheapest quote conflicts with delivery constraint → choose feasible alternative with evidence.
7. Quote lookup timeout → bounded retry then fail safely.
8. Duplicate purchase request → idempotency prevents duplicate write.
9. Prompt injection inside supplier note → content cannot override tool permission/policy.
10. Agent selects write tool before required checks → deterministic validator blocks it.
11. Quote expired → re-query or return controlled failure.
12. PO-draft write succeeds but verification fails → report partial failure; do not claim completion.

### Validation result
- Deterministic oracle available for all 12 cases: **12/12**.
- Week-2 slice can use 4 tools and one request write without real ERP/SaaS: **PASS**.
- Business value explanation: “turn a fuzzy purchase need into a checked, comparable, approval-ready purchase request” — understandable without domain training: **PASS**.
- Main unresolved assumption: direct procurement-specific hiring evidence is thinner than general enterprise Agent evidence.

## C5 Financial operations validation

### Bounded domain
Use internal expense/payment exception processing only. Explicitly exclude investment advice, trading, credit decisions and claims of regulatory compliance.

Entities: expense/payment_record, employee/vendor, policy, limit, exception_case, approval, audit_log.

Minimal tools:
1. `payment_lookup`
2. `policy_search`
3. `limit_check`
4. `vendor_check`
5. `create_exception_case`
6. `request_approval`
7. `apply_allowlisted_resolution`

### 12 evaluable cases
1. Valid low-risk exception → create case and recommended action.
2. Missing supporting evidence → request missing input.
3. Policy conflict → escalate rather than resolve automatically.
4. Limit exceeded → require approval.
5. Vendor mismatch → block write and create review case.
6. Duplicate exception submission → idempotency prevents duplicate case.
7. Policy retrieval timeout → safe failure/no action.
8. Prompt injection in memo/attachment → cannot alter permission or policy.
9. Wrong resolution tool → deterministic policy validator blocks it.
10. High-risk action requested → Human-in-the-loop required.
11. Conflicting policy versions → surface ambiguity and escalate.
12. Action write succeeds but audit verification fails → controlled partial-failure state.

### Validation result
- Deterministic oracle available for all 12 cases: **12/12**.
- Week-2 slice is technically possible: **PASS**.
- Business value is clear, but domain boundary requires more explanation than C1 and safety wording is easier to overclaim.
- Stronger direct hiring evidence than C1, but higher scope/communication risk.

## C2 fallback sanity check

A thin incident simulator with seeded logs/deployments and one allowlisted remediation is evaluable, but preserving a credible incident story without drifting into Kubernetes/observability/platform construction remains a larger implementation burden than C1.

## Post-validation score adjustments

Validation changes only dimensions directly tested:

| Candidate | Demand | Agent depth | Interview | Feasibility | Background fit | Differentiation | Revised center |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 | 8.0 | 9.0 | 9.4 | 9.4 | 9.3 | 9.2 | **8.94** |
| C5 | 9.1 | 8.9 | 9.0 | 7.9 | 8.6 | 8.5 | **8.75** |
| C2 | 8.7 | 9.2 | 9.3 | 7.8 | 8.8 | 8.4 | **8.765** (unchanged) |

## Decision

The bounded validation improves confidence that C1 has the cleanest two-week slice and lowest domain overhead, but **does not create a >0.5 decisive lead**. C1 is therefore allowed to become a **conditional first recommendation**, not a certain winner.

US3 must attack C1 independently and explicitly compare it with C2 and C5. If red-team evidence materially weakens procurement demand/Agent necessity, or shows the project collapses into deterministic rules, switch to C2 or C5 rather than defending C1 by adding scope.
