# Candidate Portfolio

Input: `artifacts/market/capability-map.md` after Gate 1 PASS.

All candidates must prove a business task, genuine Agent judgment, Tool/API execution, deterministic business state, evaluation feasibility, and a solo 6–8 week boundary.

## C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent

- **Business problem**: translate fuzzy purchase needs into supplier options, policy/budget checks and approvals.
- **Agent necessity**: clarify needs, decide what evidence/tool is needed next and compare tradeoffs.
- **Business system**: suppliers, quotations, budgets, policies, approvals, purchase requests.
- **Core slice**: `request → supplier/quote/budget/policy tools → recommendation → approval → purchase request`.
- **Strength**: strong backend/state/eval story.
- **Fatal risk**: large parts of the workflow can be reduced to deterministic ERP/workflow logic; the business pain and non-substitutability of the Agent are weaker than initially assumed.

## C2 — DevOps/R&D Incident Diagnosis & Remediation Agent

- **Business problem**: engineers triage incidents across alerts, logs, runbooks, deploys and change history.
- **Agent necessity**: dynamically choose evidence, form/test hypotheses and select safe remediation/escalation.
- **Business system**: service catalog, logs/metrics, deployments, issues, runbooks and safe remediation actions.
- **Core slice**: `incident → inspect evidence → hypothesize → tool loop → approval → remediation → verify`.
- **Strength**: strongest technical Agent mapping.
- **Fatal risk**: overlaps materially with the user's existing OpsPilot_Agent portfolio and can overgrow into infrastructure work.

## C3 — Data/BI Decision-to-Action Agent

- **Business problem**: ambiguous business questions require metric resolution, querying, validation and controlled follow-up action.
- **Agent necessity**: clarify intent, select data/analysis steps, detect insufficient evidence and decide a follow-up action.
- **Business system**: analytics DB, metric definitions, report/task records and controlled action API.
- **Core slice**: `question → metric/schema/query tools → validate → explain → optional action task`.
- **Fatal risk**: can collapse into ordinary Text-to-SQL unless the decision/action layer is central.

## C4 — Enterprise Email / Internal Workflow Execution Agent

- **Business problem**: employees turn unstructured messages into tasks, approvals and follow-ups across internal systems.
- **Agent necessity**: infer intent, recover missing context and select the correct workflow/tool.
- **Business system**: messages, tickets/tasks, policy knowledge and approvals.
- **Core slice**: `message → classify/parse → retrieve context → workflow/tool → approval → task update`.
- **Fatal risk**: common assistant pattern and weaker business differentiation.

## C5 — Financial Operations / Policy Compliance Execution Agent

- **Business problem**: operational exceptions require combining transaction data, policy, risk classification and approvals.
- **Agent necessity**: gather evidence, interpret exception intent, classify risk and choose escalation/action.
- **Business system**: synthetic transactions, limits, policy, exception cases and audit records.
- **Core slice**: `exception → transaction/policy evidence → risk → deterministic validation → approval/action`.
- **Fatal risk**: domain and safety explanation burden is high for a two-month student project.

## C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent

- **Business problem**: a human after-sales agent often has to understand an ambiguous complaint, identify the right order, inspect order state, inspect logistics, retrieve applicable after-sales policy, determine the correct business path, create a refund/return/work-order action and escalate exceptional/high-risk cases. The customer experiences this today as repeated questions and manual cross-system handoffs.
- **Target users**: e-commerce consumer; customer-service/after-sales operator; human approver for high-risk exceptions.
- **Business system**: users, orders, order items, logistics events, after-sales policies, refund/return eligibility service, refund requests, return requests, work orders, approval records and audit logs.
- **Agent necessity**: the next step is not fixed. The Agent must resolve intent/order context, decide which evidence is missing, choose order/logistics/policy/after-sales tools dynamically, distinguish logistics anomaly vs delivered-return vs unsupported case, and decide whether to ask a clarification, execute an allowed action or escalate to a human.
- **Deterministic boundary**: the LLM never authorizes money movement. Refund eligibility, amount, order-state transition, permission, idempotency and write validation are server-side deterministic rules. RAG explains/retrieves policy; it does not grant refund authority.
- **Not just chat**: successful runs create or update a real synthetic business object such as `RefundRequest`, `ReturnRequest` or `SupportTicket`, or deliberately leave state unchanged when policy/permission fails.
- **Core vertical slice**: `user complaint → identify order → inspect order/logistics → retrieve policy if needed → deterministic eligibility → Agent chooses refund/return/escalation → approval if required → write tool → verify state → result + trace`.
- **Evaluation feasibility**: very high. Order/logistics/policy states can be reset deterministically; expected tools, parameters, forbidden actions and final business state can all be scored without a subjective judge for most cases.
- **8-week core**: one after-sales domain only; 6–8 tools; refund, return and logistics-anomaly paths; one human-approval threshold; 60–80 eval cases; full failure/security/trace path. Explicitly cut product recommendation, pre-sales QA, marketing, merchant operations, real payment gateway and broad omnichannel customer service.
- **Hiring evidence**: strict-core market evidence already supports Tool/API execution, stateful Agent workflows, backend engineering, RAG, eval and observability. Supplementary current e-commerce hiring descriptions explicitly mention intelligent customer service and after-sales/refund/logistics Agent scenarios; these are supporting context rather than part of the strict 30-posting denominator.
- **Role mapping**: Agent Application Engineer, AI Backend, AI Full Stack, e-commerce AI application, customer-service Agent, enterprise Tool integration and evaluation/reliability roles.
- **Fatal risks**: if the implementation degenerates into `intent → fixed refund API`, Agent necessity disappears; this must be prevented by multi-evidence branching scenarios and an explicit deterministic/Agent boundary.

## Candidate state

C1–C5 remain evaluated alternatives. C6 is the current recommended candidate after reopening the decision in response to a P0 business-value challenge against C1. Final selection is recorded in `artifacts/decisions/final-selection.md`.