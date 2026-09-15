# Red-team Rescore — Selection Reopened

## Why this file changed

The original three-role review did not fully eliminate a P0 concern against C1: the procurement project could still be summarized as “ERP/workflow automation with an LLM wrapper.” The user's direct challenge triggered a legitimate reopen under the existing decision rules.

## Reassessment

### C1 Procurement
- Demand: 8.0
- Agent depth: **7.6** after P0 downgrade
- Interview value: **8.4**
- Feasibility: 9.2
- Background fit: 9.2
- Differentiation: **8.0**
- Revised center: **8.30**

Reason: deterministic budget/eligibility/approval/state logic dominates the core; Agent value exists but is not the strongest headline.

### C6 CommerceAgent — After-sales Execution
- Demand: 9.4
- Agent depth: 9.3
- Interview value: 9.5
- Feasibility: 9.3
- Background fit: 9.3
- Differentiation: 8.8
- Center: **9.29**

Reason: ambiguous customer request + order resolution + logistics evidence + policy context + deterministic eligibility + safe state-changing actions create a naturally branching task. It is also straightforward to build deterministic eval oracles.

## Fatal-gate recheck for C6

1. **Two-week vertical slice** — PASS: order/logistics/eligibility/refund local stack is bounded.
2. **No inaccessible private dependency** — PASS: synthetic/local contract-realistic systems are sufficient.
3. **Real Agent judgment** — PASS with condition: Week 2 must show evidence-dependent next-tool/action decisions, not fixed routing.
4. **Offline evaluability** — PASS: resettable order/logistics/policy state and exact write predicates.
5. **Reliability/security/observability in 8 weeks** — PASS with strict after-sales-only scope.
6. **60-second business clarity** — PASS: “not answer how to refund; actually diagnose and safely execute after-sales.”

## Portfolio check

C2 remains technically strong, but the user's existing OpsPilot_Agent makes another incident/DevOps Agent less valuable as a second portfolio anchor. C6 complements it with customer-facing commerce, Java transactional backend, money/state safety and deterministic evaluation.

## Result

**C6 becomes SELECTED. C1 becomes SUPERSEDED.**

This is not a cosmetic rename; downstream A–Q, Tool contracts, scenarios, eval and roadmap must all use after-sales semantics.
