# Validation — CommerceAgent Agent-Value Gate

The earlier procurement-vs-finance tie-break is obsolete for the current selection and is replaced by the implementation-facing validation that matters now.

## Validation question

Can the same refund-like user request produce materially different next tools/actions when the business evidence changes?

## Four seeded cases

1. `SHIPPED + unsigned + logistics stalled` → refund eligibility → refund path.
2. `DELIVERED + return window open` → return eligibility → return path.
3. `two matching orders` → clarification; no business write.
4. `eligible + high-risk amount` → Human-in-the-loop approval; no write before approval.

## PASS condition

CommerceAgent passes only if the Agent uses intermediate Tool Results to choose different next paths and the deterministic backend prevents illegal state changes.

## FAIL condition

If all cases collapse to `intent=refund → fixed refund endpoint`, the project fails its Agent-value hypothesis.

## Required response to FAIL

Do not add MCP, Multi-Agent, K8s or more prompts. Redesign the Agent/business boundary or reopen project selection.

## Current status

**DESIGN PASS / IMPLEMENTATION VALIDATION PENDING.** The formal `002-commerce-after-sales-agent/spec.md` encodes this as an implementation success criterion.