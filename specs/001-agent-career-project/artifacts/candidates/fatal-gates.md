# Candidate Fatal Gates

A weighted score cannot compensate for any failed gate.

| Candidate | 2-week vertical slice | No inaccessible core dependency | Genuine Agent judgment | Offline eval feasible | Reliability/security/obs in 8 weeks | 60-sec business value | Verdict |
|---|---|---|---|---|---|---|---|
| C1 Procurement & Supplier Execution | PASS — one category, 4–6 local tools | PASS — synthetic suppliers/quotes/budgets/policies | PASS — incomplete requirements, dynamic information gathering, tradeoff/approval decision | PASS — deterministic business state + policy oracles | PASS if real ERP/SaaS and Multi-Agent are cut | PASS | **PASS** |
| C2 DevOps/R&D Incident Agent | PASS — simulated service + injected fault + one safe action | PASS — local service/log/deployment simulator | PASS — hypothesis/evidence/tool/remediation choice | PASS — golden root cause + expected post-health state | PASS only if cluster/K8s/general Code Agent scope is cut | PASS | **PASS with scope constraint** |
| C3 Data/BI Decision-to-Action | PASS — one domain DB + metric/query/action tools | PASS — synthetic relational dataset | PASS — ambiguous metric intent, query/validation/action choice | PASS — fixed DB state + query/result/action predicates | PASS — policy + tool safety + trace are compact | PASS | **PASS** |
| C4 Email/Internal Workflow Agent | PASS — synthetic inbox + task/policy tools | PASS — no Gmail/Outlook OAuth required | PASS — intent/context/workflow/approval choice | PASS — message/task golden states | PASS — permissions, injection and duplicate writes can be tested locally | PASS | **PASS** |
| C5 Financial Operations/Policy Compliance | PASS — one synthetic exception workflow | PASS — no real bank API or confidential data | PASS — evidence gathering, policy interpretation, risk/escalation choice | PASS — synthetic transactions + explicit policies | PASS if restricted to operational workflow and allowlisted writes | PASS | **PASS with domain constraint** |
| C6 Merchant/E-commerce Operations | PASS — one merchant issue + 5 tools | PASS — synthetic catalog/inventory/campaign data | PASS — signal gathering, diagnosis and action choice | PASS — seeded issue/action pairs | PASS if recommendation/ads/training subsystems are excluded | PASS | **PASS with scope constraint** |

## Gate notes

### C1
The main risk is not feasibility but evidence specificity: strict-core hiring evidence supports enterprise execution, supply-chain/operations and business-system integration, but not a broad claim that procurement Agent roles are common. This affects demand score, not fatal feasibility.

### C2
Infrastructure is a scope trap. The candidate remains eligible only if “incident Agent” is implemented against a small deterministic service simulator instead of requiring a real Kubernetes/observability platform.

### C3
To remain eligible, it must demonstrate an action/decision layer; a read-only NL2SQL chatbot would fail the Agent Value Gate.

### C4
Real email-provider integration is explicitly non-core. The hiring signal is enterprise workflow execution, permission and evaluation, not OAuth plumbing.

### C5
The project must avoid investment advice, credit decisions or claims of regulatory compliance. It remains a synthetic internal operations/policy workflow with explicit approval and audit.

### C6
Commerce breadth is explicitly rejected. One workflow only; no recommender training, ad bidding, customer-service suite, logistics suite or broad merchant platform.

**Fatal-gate outcome**: all six candidates are eligible for scoring, with the documented scope constraints treated as binding conditions.
