# Execution Artifacts

This directory contains the executable outputs of `001-agent-career-project`.

## Source of truth
- `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/artifact-contracts.md`, and `quickstart.md` remain design inputs.
- This `artifacts/` tree records execution evidence, intermediate analysis, decisions, and exit-gate reports.
- External facts must include direct/authoritative source URLs and observation date where available.
- Facts, inferences, recommendations, assumptions, and targets must be distinguishable.

## Structure
- `market/`: job evidence, exclusions, audit, capability map.
- `candidates/`: candidate portfolio, fatal gates, scores, sensitivity.
- `decisions/`: decision log, red-team memos, final selection.
- `final-project/`: A–Q project specification and implementation/interview plan.
- `career/`: resume/README/demo templates and evidence-backed claims.

## Current status
| Stage | Status |
|---|---|
| Setup | complete |
| Foundational rules | complete |
| US1 market evidence | complete — Gate 1 PASS |
| US2 candidate portfolio | complete — Contract 2 PASS with explicit uncertainty |
| US3 red team | complete — Contract 3 PASS; ProcurePilot selected |
| US4 final project spec | complete — Contract 4 PASS |
| US5 roadmap/interview | complete — implementation/interview plan PASS |
| US6 career materials | complete — templates only; metrics remain targets |
| Cross-cutting traceability/integrity | complete |
| Local Spec Kit active-feature pointer | action required before next local implementation workflow (`.specify/feature.json` absent in GitHub repo) |

## Final decision

`001-agent-career-project` is ready for review/merge as a research-and-design feature. The selected project is **ProcurePilot: Enterprise Procurement & Supplier Execution Agent**.

Application code is intentionally not part of this feature. After review/merge, create/select a separate implementation feature (suggested logical name: `002-procurepilot-implementation`) through the local Spec Kit workflow, then generate its implementation tasks from the final A–Q specification, scenarios, tool contracts, evaluation design, and 6+2 week roadmap.
