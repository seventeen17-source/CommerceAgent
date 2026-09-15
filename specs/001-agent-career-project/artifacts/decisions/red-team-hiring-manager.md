# Red Team — Hiring Manager Elimination Memo

Target: C1 Procurement & Supplier Execution Agent. Alternatives: C2 DevOps/R&D Incident, C5 Financial Operations.

| issue_id | severity | challenge | evidence / failure scenario | proposed disposition |
|---|---|---|---|---|
| HM-01 | P1 | Does procurement map directly enough to the target role family? | Market evidence strongly supports Tool/API, workflow, eval and enterprise integration, but C2 has more direct R&D/platform/AI-Coding job mapping and C5 has denser finance-domain hiring evidence | **compare alternatives and lower C1 demand confidence** |
| HM-02 | P1 | Will a hiring manager understand the value in 60 seconds without procurement expertise? | “fuzzy request → supplier/quote/budget/policy → approval-ready request” is understandable, but terminology such as sourcing/PO can distract if overdone | **simplify narrative**: one purchase-request workflow, common terms, one measurable outcome loop |
| HM-03 | P1 | Does a local synthetic procurement system look fake? | No real ERP/vendor credentials are available; a stateless mock would undermine enterprise credibility | **retain contract-realistic local system** with persistent supplier/quote/budget/request/approval state, transactions, audit and idempotency; README must call it synthetic/local |
| HM-04 | P1 | Is there a more role-adjacent problem that shows faster onboarding? | C2 mirrors R&D efficiency/platform/Agent backend responsibilities visible in multiple core postings and is closer to daily software-engineering work | **promote C2 as active challenger** rather than treating it as runner-up decoration |
| HM-05 | P2 | Is broad “procurement platform” scope necessary? | Broad sourcing, contracts, inventory, logistics and supplier lifecycle would make the project less credible in 6–8 weeks | **delete breadth**: one category, request-to-approval/PO-draft workflow only |

## Hiring-manager verdict

C1 has clear enterprise value and a good business-state loop, but it is **not the strongest direct hiring-domain match**. C2 deserves a higher role-mapping score after scope is reduced to a small incident simulator. If C2 can preserve the same reliability/eval evidence without infrastructure sprawl, a hiring manager would likely find it more immediately connected to software/AI engineering responsibilities.
