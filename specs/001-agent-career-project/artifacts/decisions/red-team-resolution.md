# Red-Team Resolution

The three reviews were written independently before consolidation. C2 and C5 remain explicit alternatives.

| issue_id | severity | disposition | Concrete action | Score/scope impact | Residual risk |
|---|---|---|---|---|---|
| INT-01 Agent vs CRUD | P0 | validate + narrow | Freeze boundary: Agent may resolve ambiguity, choose evidence/tools, compare constrained alternatives and decide escalation; deterministic backend owns eligibility, money, permissions, state transitions and writes. Evaluation must include cases where dynamic next-action choice matters | C1 Agent depth 9.0 → 8.8 until implemented evidence exists | If actual workflow reduces to fixed form steps, switch project |
| INT-02 procurement hiring specificity | P1 | accept risk | Describe project as enterprise execution Agent in hiring mapping; do not claim “procurement Agent” is a common job category | C1 demand 8.0 → 7.8 | Direct procurement-title evidence remains limited |
| INT-03 failure depth | P1 | retain Must | Timeout/retry, wrong tool/parameter, duplicate/idempotency, injection/permission, approval and partial failure remain core | no cut | Implementation quality still unproven until later feature |
| INT-04 subjective supplier recommendation | P1 | redesign | Eval with hard constraints, allowed/forbidden calls, business-state predicates and acceptable-choice sets rather than exact prose | C1 eval credibility preserved | Some tradeoff explanations remain qualitative |
| INT-05 arbitrary language split | P1 | defer technology | No Java/Python split is frozen in this feature; later tech decision must justify service boundary | no architecture theater allowed | Implementation feature may still choose one or two languages |
| INT-06 MCP/Multi-Agent buzzwords | P2 | downgrade/delete | MCP = Should; Multi-Agent = Reject by default; K8s/queue/cache = Reject unless evidence changes | reduces scope | Less keyword breadth, intentionally |
| HM-01 role mapping | P1 | rescore | Lower C1 demand confidence and explicitly compare C2/C5 | reflected in final scores | C1 remains less direct than finance/R&D domain mapping |
| HM-02 narrative clarity | P1 | simplify | One purchase-request workflow only; no sourcing suite/contract lifecycle/inventory/logistics | interview score remains high | Requires disciplined README/demo language |
| HM-03 synthetic system credibility | P1 | strengthen local system | Persistent contract-realistic supplier/quote/budget/request/approval/audit state; clearly disclose synthetic/local boundary | feasibility remains high | No production ERP claim permitted |
| HM-04 C2 as stronger role-adjacent alternative | P1 | compare then downgrade for portfolio overlap | C2 technically maps well, but it materially overlaps the existing `OpsPilot_Agent` portfolio direction; reduce differentiation/marginal portfolio value for this user | C2 differentiation 8.4 → 6.8 | If OpsPilot is abandoned, C2 should be reconsidered |
| HM-05 broad procurement scope | P2 | delete | Keep one category and request→approval/PO-draft flow | C1 feasibility 9.4 → 9.3 after realistic backend requirements | none material |
| DEV-01 toy data | P1 | strengthen deterministic backend | Add quote validity, budget reservation/check, state machine, audit and idempotent writes to spec | preserves interview depth | Must remain implementable in six core weeks |
| DEV-02 non-deterministic recommendation | P1 | redesign | Constraint-first facts + acceptable-choice predicates + explicit uncertainty | preserves eval feasibility | subjective tie cases need documented policy |
| DEV-03 duplicate/partial writes | P1 | retain Must | Idempotency key, verify-after-write, bounded retry policy, partial-failure state | security/reliability stays core | requires careful implementation later |
| DEV-04 injection via retrieved text | P1 | retain Must | Treat retrieved text as untrusted; permissions/policy server-side; source/version metadata | security stays core | adversarial eval required |
| DEV-05 real SaaS/ERP | P2 | delete from core | external adapter only Should after local contract passes | improves feasibility | less production-integration spectacle |
| DEV-06 excess infra | P2 | delete/downgrade | Multi-Agent/K8s/queue/cache rejected; MCP optional Should | reduces complexity | none |
| DEV-07 C2 cleaner causal eval | P1 | accept technical merit, compare portfolio value | Keep C2 as fallback; its seeded-fault eval is strong, but portfolio redundancy reduces marginal value | C2 interview remains high; differentiation reduced | revisit if existing OpsPilot is not used for recruiting |

## C5 comparison resolution

C5 retains the strongest direct finance-domain evidence, but red-team review confirms higher domain/safety explanation burden and lower background fit for a general backend/Agent candidate. Keep C5 as second alternative, not default selection. No finance-specific claims or real-bank integration should be introduced merely to improve score.

## P0 status

INT-01 is **resolved conditionally** by an explicit Agent/deterministic boundary plus a future evaluation requirement. It becomes P0 again if the A–Q design cannot specify at least several cases where next-action/tool/evidence choice is genuinely dynamic and independently testable.

No other unresolved P0 remains.
