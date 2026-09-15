# Quickstart Validation

Validation target: `specs/001-agent-career-project/quickstart.md`.

## Scenario 1 — Active feature and required files

- `spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`, `checklists/` and `tasks.md` exist in the repository/feature branch.
- The GitHub repository does **not** currently contain `.specify/feature.json`; earlier read returned Not Found.

**Result: PARTIAL / local Spec Kit precondition outstanding.**

This does not invalidate the explicit GitHub artifact path used in this execution, but before running local Spec Kit commands for the next implementation feature, the local workspace must select/create the active feature so `.specify/feature.json` (or the current Spec Kit equivalent) resolves correctly.

## Scenario 2 — No unresolved specification placeholders

The feature spec/plan/research used for task generation contain the intended concrete feature content. The repository constitution is still a generic placeholder template, which `plan.md` already declares non-operative; it is not treated as a hidden governance source.

**Result: PASS for the feature artifacts, with constitution-template caveat already documented in plan.**

## Scenario 3 — Stage gates

1. Candidate scoring was not finalized before 30 strict A/C core samples and source audit: PASS.
2. First recommendation followed fatal gates: PASS.
3. Final selection/A–Q followed three independent red teams: PASS.
4. Resume numbers remain targets because there are no real evaluation runs: PASS.

**Result: PASS.**

## Scenario 4 — Recalculate candidate scoring

The fixed formula is used in `candidates/scoring.csv` and `decisions/red-team-rescore.md`. Fatal gates are non-compensatory. Close-ranking overlap triggered bounded validation rather than an automatic winner.

**Result: PASS.**

## Scenario 5 — Red team changes decisions

Examples of actual effects:
- C1 procurement demand score reduced due weaker scenario-specific hiring evidence.
- C1 Agent-depth assumption reduced and converted into a future implementation/eval gate.
- MCP downgraded to Should; Multi-Agent/K8s/queue/cache rejected from core.
- broad procurement-suite scope deleted.
- C2 differentiation reduced because of portfolio overlap with existing OpsPilot direction.
- C2/C5 remained real switch candidates through the final rescore.

**Result: PASS.**

## Scenario 6 — Two-month feasibility

- Week 2 includes happy + controlled-failure vertical slice: PASS.
- Every week has runnable output and acceptance: PASS.
- Must/Should/Nice/Reject and cut order: PASS.
- evaluation/security/reliability/observability enter Weeks 1–4 rather than the last week: PASS.

**Result: PASS at planning level.**

## Scenario 7 — Resume integrity

All result metrics in `career/evidence-backed-resume-claims.md` remain `target` and use `[待实测]` placeholders. Promotion to measured/approved requires run refs, dataset version, metric formula and limitations.

**Result: PASS.**

## Overall quickstart verdict

**6 scenarios PASS; Scenario 1 is PARTIAL because `.specify/feature.json` is absent from the GitHub repository.**

Decision/research artifacts are ready for review. Before invoking the next local Spec Kit implementation workflow, fix/select the local active-feature pointer rather than inventing one in this branch without knowing the local CLI state.
