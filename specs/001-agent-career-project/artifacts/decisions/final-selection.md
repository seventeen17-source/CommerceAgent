# Final Project Selection

## Selected candidate

**C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent**

Status: **SELECTED after decision reopen and red-team challenge**.

The previous C1 ProcurePilot selection is **SUPERSEDED**, not deleted. The change was triggered by a P0 challenge: procurement could be explained too easily as deterministic ERP/workflow automation with an LLM wrapper, making the Agent necessity and business pain less convincing than required for the user's primary portfolio project.

## Decision change

### Previous selection
C1 — ProcurePilot: Enterprise Procurement & Supplier Execution Agent.

### Reopen trigger
The user challenged the central value proposition: “这个解决不了什么”. Re-evaluation confirmed that the procurement design's strongest mechanics—budget checks, supplier eligibility, approval thresholds, PO state transitions—are predominantly deterministic. The Agent still adds value for requirement clarification and evidence selection, but that value is too thin for the project's headline.

### New selection
C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent.

The new problem is sharper: a customer presents an ambiguous after-sales goal, while resolution requires dynamic evidence gathering across order state, logistics, after-sales policy, eligibility, risk/approval and write systems. The correct next tool and business path vary by evidence.

## Core business problem

Human after-sales agents repeatedly perform this cross-system loop:

`understand complaint → identify order → inspect order state → inspect logistics → retrieve relevant policy → determine refund/return/escalation path → execute or route approval → verify result`

CommerceAgent automates that orchestration while keeping money, permissions and state transitions under deterministic backend authority.

Example task:

> “我 9 月 10 日买的耳机到现在没收到，我不要了，帮我退款。”

A valid Agent run must not simply answer with instructions. It must identify the relevant order, inspect delivery/logistics state, obtain applicable policy evidence when necessary, call deterministic refund-eligibility logic, choose refund/return/escalation, execute an allowed write or request approval, then verify the resulting business state.

## Why Agent is necessary

The Agent owns uncertainty and orchestration:
- infer the after-sales intent and resolve ambiguous order references;
- decide which evidence is still missing;
- choose the next Tool/API dynamically;
- distinguish logistics anomaly, delivered-return, non-refundable item and exceptional case;
- decide whether clarification, policy retrieval, write execution, human approval or escalation is the next step;
- synthesize an auditable explanation from the evidence actually used.

The Agent does **not** own deterministic authority.

## Deterministic backend boundary

The business backend remains authoritative for:
- user/order ownership and permissions;
- refund/return eligibility;
- refundable amount and financial limits;
- legal state transitions;
- idempotency and duplicate-write protection;
- high-risk approval thresholds;
- actual creation of refund/return/work-order records;
- audit log integrity.

**RAG retrieves/explains policy; it does not authorize a refund.**
**The LLM may propose an action; the backend decides whether that action is legal.**

## Core vertical slice

`User complaint → Agent → identify_order → get_order → get_logistics → policy_search (conditional) → check_after_sales_eligibility → choose refund/return/escalation → approval (conditional) → create_refund/create_return/create_ticket → verify_business_state → Result + Trace`

## Why this beats C1 now

1. **Harder business pain**: cross-system after-sales exception handling is a recognizable high-volume operational problem, not merely a convenience layer.
2. **Stronger Agent necessity**: the next action genuinely depends on intermediate evidence rather than a mostly fixed workflow.
3. **Cleaner Agent/backend separation**: LLM handles ambiguity and orchestration; deterministic services handle money, permissions and state safety.
4. **Better evaluation**: order/logistics/policy states permit deterministic oracles for expected tools, parameters, forbidden actions and final state.
5. **Stronger interview story**: timeout + idempotency, Prompt Injection, high-risk approval, wrong-tool prevention and post-write verification naturally arise from the business problem.
6. **Better portfolio differentiation**: unlike C2, it does not duplicate the user's existing OpsPilot_Agent theme.

## Revised ranking

| Rank | Candidate | Center score | Decision |
|---:|---|---:|---|
| 1 | C6 E-commerce After-sales Execution & Exception Handling | **9.29** | SELECTED |
| 2 | C5 Financial Operations / Policy Compliance | 8.86 | Alternative; higher domain/safety burden |
| 3 | C3 Data/BI Decision-to-Action | 8.655 | Alternative; risk of looking like Text-to-SQL |
| 4 | C2 DevOps/R&D Incident Agent | 8.625 | Strong but portfolio-overlap penalty |
| 5 | C4 Enterprise Workflow | 8.50 | Feasible but less distinctive |
| 6 | C1 Procurement & Supplier Execution | 8.30 | Superseded due weak headline Agent necessity |

Scores are planning judgments, not measured product outcomes.

## MVP boundary

Core version includes only after-sales execution:
- order identification and lookup;
- logistics status/anomaly lookup;
- policy retrieval with citations where non-structured policy is needed;
- deterministic refund/return eligibility;
- refund/return/work-order writes;
- one high-risk Human-in-the-loop approval path;
- retries, idempotency, authorization, Prompt Injection resistance;
- per-run trace and 60–80 offline evaluation cases.

Explicitly excluded from core:
- product recommendation;
- pre-sales FAQ;
- generic shopping assistant;
- merchant marketing/ads;
- procurement;
- real payment gateway;
- broad omni-channel customer service;
- Multi-Agent;
- Kubernetes/complex infrastructure.

## Revisit triggers

Reopen this decision if any of the following occurs:
- the implemented flow collapses into `intent → fixed refund API` with no meaningful evidence-dependent next-step decisions;
- deterministic eval cases cannot distinguish Agent behavior from a simple rules router;
- obtaining a realistic synthetic order/logistics/after-sales backend proves infeasible within Week 2;
- new hiring evidence materially favors another candidate while C6 loses its Agent-depth advantage.

## Contract 3 verdict

**PASS after reopen.** The original recommendation was challenged, the challenge changed the decision, and the final selection now has a clearer business problem, stronger Agent necessity, bounded deterministic authority and an independently testable two-month scope.
