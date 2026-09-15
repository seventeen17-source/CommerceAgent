# Candidate Portfolio

Input: `artifacts/market/capability-map.md` after Gate 1 PASS.

All candidates are intentionally technology-neutral at this stage. Each must prove a business task, Agent necessity, Tool/API execution, deterministic business state, evaluation feasibility, and a solo 6–8 week boundary.

## C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent

- **Business problem**: employees/procurement staff spend time translating fuzzy purchase needs into comparable supplier options, checking policy/budget, collecting evidence, and routing approvals across disconnected systems.
- **Target users**: requester, procurement specialist, budget owner/approver.
- **Business system**: suppliers, quotations, purchase requests, budgets, policy documents, approval state, purchase-order draft records.
- **Agent necessity**: interpret incomplete natural-language needs, identify missing constraints, decide which information/tool is needed next, compare tradeoffs, explain risks, and decide when human approval is required.
- **Not just chat**: creates/updates a purchase request or PO draft only after deterministic checks and approval rules.
- **Core vertical slice**: `request → normalize need → supplier_search → quote_query → budget_check → policy_check → recommendation → approval → purchase_request/PO_draft → result + trace`.
- **Evaluation feasibility**: high; synthetic suppliers/quotes/budgets/policies provide deterministic expected states and tool/parameter checks.
- **8-week core**: one procurement category, 4–6 tools, one approval policy, local contract-realistic backend, 50–80 eval cases, failure/security paths. Cut ERP/SAP integration, multi-Agent, advanced UI, real supplier APIs.
- **Fatal risks**: weak direct procurement-title hiring evidence; can become a glorified rules engine if Agent judgment is not sharply defined.
- **Role mapping**: Agent application, AI backend, enterprise integration/FDE; especially strong for Java/backend + Agent narrative.

## C2 — DevOps/R&D Incident Diagnosis & Remediation Agent

- **Business problem**: engineers triage incidents across alerts, logs, runbooks, deployment state, recent changes, and service ownership; diagnosis and safe remediation are slow and repetitive.
- **Target users**: backend/platform engineers, on-call/SRE, engineering productivity teams.
- **Business system**: service catalog, deployment history, logs/metrics, issue tracker, runbooks, change records, safe remediation actions.
- **Agent necessity**: dynamically choose evidence sources, form/test hypotheses, decide whether evidence is sufficient, select a safe remediation or escalation path.
- **Not just chat**: may create incident records, propose/execute allowlisted low-risk remediation, or roll back a controlled sandbox deployment after approval.
- **Core vertical slice**: `incident → inspect service/deploy/logs → hypothesize → query tools → risk check → human approval if write → remediation → verify health → incident report + trace`.
- **Evaluation feasibility**: high with deterministic simulated services, injected faults, golden root causes, allowed actions and expected post-state.
- **8-week core**: 3 fault families, 5–7 tools, one safe-write action, local service simulator, 50–80 eval cases. Cut Kubernetes cluster integration, general coding agent, broad observability stack.
- **Fatal risks**: easy to overbuild infrastructure; must avoid becoming generic log summarization or a full Code Agent.
- **Role mapping**: Agent framework/backend, platform, AI coding/R&D efficiency, evaluation/observability.

## C3 — Data/BI Decision-to-Action Agent

- **Business problem**: business users ask ambiguous analytical questions that require choosing data sources, generating/validating queries, interpreting results, applying policy, and sometimes triggering a follow-up business action.
- **Target users**: operations analyst, business owner, data platform user.
- **Business system**: relational analytics data, metric definitions, business rules, report/task records, controlled action API.
- **Agent necessity**: clarify intent, map business language to metrics, choose query/analysis steps, validate anomalies, decide when evidence is insufficient, and translate analysis into an allowed action.
- **Not just chat**: produces a verifiable report and can create an action/task record based on deterministic thresholds and approval.
- **Core vertical slice**: `business question → metric/context resolution → schema/SQL tools → validate result → explain → optional create_action_task → result + trace`.
- **Evaluation feasibility**: very high; fixed database states, expected SQL/result predicates, allowed/forbidden actions and metric definitions.
- **8-week core**: one domain dataset, 5 tools, 15–20 metrics, optional document retrieval for metric policy, 60–100 eval cases. Cut general-purpose text-to-SQL platform and multi-database federation.
- **Fatal risks**: may look like Text-to-SQL/RAG unless the decision/action layer, failure checking and business-state change are central.
- **Role mapping**: Data Agent, AI backend, enterprise integration, evaluation-heavy roles.

## C4 — Enterprise Email / Internal Workflow Execution Agent

- **Business problem**: employees lose time turning unstructured email/messages into tasks, gathering related knowledge/data, routing approvals, and following up across internal systems.
- **Target users**: operations staff, team leads, shared-service teams.
- **Business system**: inbox/message store, task/ticket system, policy/knowledge base, calendar-like availability, approval state.
- **Agent necessity**: infer intent, extract commitments/deadlines, resolve missing context, select the right internal workflow/tool, and choose when human confirmation is required.
- **Not just chat**: creates/updates tasks/tickets and approval requests with auditable source references.
- **Core vertical slice**: `message → classify/parse → retrieve context → select workflow/tool → permission/approval → create/update task → verify → user summary + trace`.
- **Evaluation feasibility**: high using synthetic messages, policies, tasks, expected tool calls and final states.
- **8-week core**: 3 workflow types, 5 tools, one write approval, 50–80 eval cases. Cut real Gmail/Outlook OAuth, broad calendar integration, polished mail client.
- **Fatal risks**: can look like a common assistant unless positioned around controlled enterprise execution, permissions and evaluation.
- **Role mapping**: enterprise Agent application, Tool integration, eval/security, full-stack.

## C5 — Financial Operations / Policy Compliance Execution Agent

- **Business problem**: internal finance/operations workflows require combining policy text, transaction/business data, exception handling and approvals; manual checks are slow but high-risk writes cannot be delegated blindly.
- **Target users**: operations analyst, finance/settlement staff, compliance reviewer.
- **Business system**: synthetic transactions, account/limit state, policy documents, exception cases, approval/audit records.
- **Agent necessity**: interpret ambiguous exception requests, gather policy and transaction evidence, classify risk, determine allowable next steps, and escalate uncertain/high-risk cases.
- **Not just chat**: creates a compliance case, proposes a resolution, or executes only allowlisted low-risk state changes after deterministic policy validation.
- **Core vertical slice**: `exception → transaction lookup → policy retrieval → risk reasoning → rule validation → approval/escalation → case/action → audit result`.
- **Evaluation feasibility**: high with synthetic finance state and explicit policy oracles.
- **8-week core**: one operational process (not trading/investment advice), 5–6 tools, one approval path, 60–80 eval cases. Cut real banking APIs and regulatory claims.
- **Fatal risks**: domain explanation burden and safety sensitivity; must stay in synthetic operational workflow, not financial advice or market prediction.
- **Role mapping**: financial AI application, Agent eval, enterprise backend, security/FDE.

## C6 — Merchant / E-commerce Operations Execution Agent

- **Business problem**: merchant operators repeatedly inspect product, inventory, campaign and performance data, diagnose issues, choose operational actions and coordinate changes across systems.
- **Target users**: merchant operator, category/operations lead.
- **Business system**: product catalog, inventory, promotion rules, performance metrics, campaign/task records.
- **Agent necessity**: interpret an operational goal, choose which signals to inspect, diagnose likely cause, compare actions, and decide whether/where to apply a change.
- **Not just chat**: creates an operation task or changes an allowlisted campaign/configuration after validation/approval.
- **Core vertical slice**: `goal/problem → inspect product/inventory/performance → diagnose → policy/tool choice → approval → create/update operation → verify → report + trace`.
- **Evaluation feasibility**: high with synthetic merchant state and golden issue/action pairs.
- **8-week core**: one merchant workflow, 5–6 tools, 60 eval cases, one controlled write. Cut recommendation-model training, ad platform integration and broad commerce suite.
- **Fatal risks**: strict-core hiring evidence is less e-commerce-specific than the discovery-only sources; scope can sprawl into recommendation/marketing/customer-service subsystems.
- **Role mapping**: Agent application, AI full-stack, enterprise operations/backend.

## Candidate state

All six candidates begin as `PROPOSED`. No candidate is selected until `fatal-gates.md`, `scoring.csv`, sensitivity analysis and (if required) bounded validation are complete.
