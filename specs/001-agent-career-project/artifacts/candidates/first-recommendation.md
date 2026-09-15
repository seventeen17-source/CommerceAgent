# First Recommendation — Current

## Recommendation

**C6 — CommerceAgent: E-commerce After-sales Execution & Exception Handling Agent**

This is the current and authoritative project recommendation.

## Why

CommerceAgent has the clearest combination of:
- real and easily explained business pain;
- genuine evidence-dependent Agent decisions;
- strong Java/backend business-state depth;
- deterministic safety boundaries for money/state changes;
- offline evaluation with reproducible business-state oracles;
- failure cases that are meaningful rather than decorative: timeout ambiguity, duplicate writes, authorization, Prompt Injection and Human-in-the-loop;
- good portfolio differentiation from the existing OpsPilot_Agent direction.

## Core MVP

`customer request → resolve order → inspect order/logistics → retrieve policy when useful → deterministic eligibility → choose refund/return/clarification/escalation/approval → guarded business write → verify state → result + trace`

## Maximum risk

The project fails its thesis if the implementation reduces to `intent → fixed refund API`.

Week 2 must therefore prove that different intermediate evidence changes the next tool or business action.

## What would change this recommendation

Reopen selection if:
- realistic synthetic order/logistics/after-sales state cannot be built inside the Week-2 boundary;
- the Agent cannot demonstrate evidence-dependent branching beyond a simple rule router;
- deterministic evaluation cannot distinguish the Agent from a basic workflow baseline;
- new hiring evidence materially weakens the after-sales/commerce mapping while another candidate becomes clearly superior.

Procurement, finance, Data Agent, internal workflow and DevOps remain rejected alternatives for this portfolio decision; they are not co-equal current recommendations.