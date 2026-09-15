# Execution Artifacts

This directory contains the executed outputs of `001-agent-career-project`.

## Source of truth
- `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/artifact-contracts.md`, and `quickstart.md` remain design inputs.
- This `artifacts/` tree records execution evidence, intermediate analysis, decisions, superseded decisions, final design, and exit-gate reports.
- External facts use direct/authoritative source URLs and observation dates where available.
- Facts, inferences, recommendations, assumptions, and future targets must remain distinguishable.

## Structure
- `market/`: job evidence, exclusions, audit, capability map.
- `candidates/`: candidate portfolio, fatal gates, scores, sensitivity.
- `decisions/`: decision log, red-team records, superseded and final selections.
- `final-project/`: authoritative CommerceAgent A–Q specification and implementation/interview plan.
- `career/`: resume/README/demo templates and evidence-backed claims.

## Current status

| Stage | Status |
|---|---|
| Setup | PASS |
| Foundational rules | PASS |
| US1 market evidence | PASS — 30 strict core postings / 20 employers |
| US2 candidate portfolio | PASS |
| US3 red team / selection | PASS — decision reopened after P0 challenge; C1 ProcurePilot superseded |
| US4 final project spec | PASS — **CommerceAgent after-sales execution Agent** |
| US5 roadmap/interview | PASS |
| US6 career templates | PASS; metrics remain targets until implementation |
| Final integrity audit | PASS with local `.specify/feature.json` caveat |

## Final project

**CommerceAgent — E-commerce After-sales Execution & Exception Handling Agent**

Core thesis:

> The Agent handles ambiguity, evidence gathering and dynamic Tool/path selection; deterministic backend services retain authority over order ownership, eligibility, amount, approvals, idempotency and money/state-changing writes.

The previous ProcurePilot design is preserved in history as a superseded decision rather than deleted, demonstrating that the red-team/decision process can actually change the outcome.

## Next step

Create a separate implementation feature (recommended: `002-commerce-after-sales-agent`) and run Spec Kit from specification through implementation there. Do not add application code to this research/decision feature.
