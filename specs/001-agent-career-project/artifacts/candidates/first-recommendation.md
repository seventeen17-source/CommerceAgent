# Conditional First Recommendation

## Recommendation

**C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent**

Status: **conditional first recommendation**, not a frozen final selection.

Post-validation center score: **8.94**. C2 and C5 remain close enough that US3 must actively attempt to replace C1.

## Why C1 is provisionally first

1. **Clean enterprise execution loop**: procurement naturally exposes structured business state (supplier, quote, budget, request, approval) plus non-structured policy knowledge.
2. **Genuine Agent boundary**: natural-language requirements are incomplete and multi-constraint; the Agent decides what information is missing, which tools to call, how to compare alternatives, and when to escalate, while deterministic code owns budget/policy/permission/state changes.
3. **Strong two-week feasibility**: a truthful local business system can reproduce the full loop without ERP credentials or paid SaaS.
4. **Interview depth without infrastructure theater**: Tool contracts, workflow/state, approval, idempotency, prompt-injection defense, eval and trace can all be discussed from one coherent task.
5. **Background fit**: a backend-strong developer can keep deterministic domain logic in a conventional backend while learning the Python/Agent layer, rather than rebuilding the whole project around unfamiliar infrastructure.
6. **Differentiation**: less generic than email assistant / PDF QA while easier to explain than a large DevOps or financial domain platform.

## Evidence mapping

Strong supporting signals come from:
- CAP002 Tool/API integration;
- CAP003 planning/workflow/state/context;
- CAP005 evaluation/observability;
- CAP006 enterprise business-system integration;
- CAP007 reliability/failure handling;
- CAP008 safe writes/approval.

Direct scenario-adjacent evidence includes Suren-Agent-2027 (operations/product/supply-chain Agent), SunPaper-AI-2027 (ERP/MES/OA/WMS integration), NAURA-Agent-J16415 (internal operations/研发效能 Agent), SouthernFund-FDE-2027 and Guoqi-AI-2026.

## Target company / role mapping

Best fit:
- Agent Application Engineer
- LLM Application Engineer
- AI Backend / Agent Backend
- AI Full Stack with business execution
- FDE / enterprise AI integration

Company types:
- enterprise software / cloud;
- industrial/manufacturing digitalization;
- finance/enterprise internal systems;
- internet/e-commerce teams building operational Agents.

## MVP vertical slice

`purchase need → normalize/missing constraints → supplier_search → quote_query → budget_check → policy_check → recommendation → create_purchase_request → conditional approval → result + trace`

Week-2 version may omit final PO creation and use one controlled write (`create_purchase_request`) plus one failure path.

## Maximum risk

**Demand specificity**: the strict-core market sample strongly supports enterprise execution Agents and supply-chain/operations use cases, but does not prove that “procurement Agent” itself is a broadly named hiring category.

If the project has to rely on generic Agent evidence while C2/C5 map more directly to job responsibilities, the recommendation should change.

## Scope reduction strategy

Cut in this order before touching the core evidence loop:
1. polished admin/UI;
2. external SaaS/ERP adapter;
3. MCP adapter (keep simple tool/API boundary);
4. second procurement category;
5. Multi-Agent;
6. long-term memory;
7. advanced deployment/cluster infrastructure.

Never cut: business-state change, tool safety, approval/idempotency, failure path, eval cases, trace/reproducibility.

## Revisit / switch triggers

Switch away from C1 if US3 shows any of:
- the Agent decision can be replaced almost entirely by deterministic rules;
- procurement-specific business value cannot be explained in 60 seconds without invented enterprise assumptions;
- credible evaluation requires unrealistic data or manual subjective grading;
- the project needs real ERP/vendor APIs to look authentic;
- C2 or C5 survives red-team review with materially stronger hiring mapping and no larger scope burden.

## Alternatives kept alive

- **C2 DevOps/R&D Incident Agent**: strongest technical/interview alternative; direct R&D/platform hiring mapping but higher infrastructure scope risk.
- **C5 Financial Operations/Policy Agent**: strongest direct hiring-domain evidence; higher domain/safety communication burden.
