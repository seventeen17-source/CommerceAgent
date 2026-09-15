# Requirements Traceability Matrix

## Functional requirements

| Requirement | Primary evidence / artifact | Status |
|---|---|---|
| FR-001 staged sequence | `stage-gates.md`, Gate reports, `final-selection.md` | PASS |
| FR-002 traceable 2026 job fields | `market/job-postings.csv`, `collection-protocol.md` | PASS |
| FR-003 target application-engineering roles / exclusions | `collection-protocol.md`, `market/exclusions.csv` | PASS |
| FR-004 separate early-career vs senior trends | `market/job-postings.csv`, `market/trend-reference.csv` | PASS |
| FR-005 contextual capability map | `market/capability-signals.csv`, `market/capability-map.md` | PASS |
| FR-006 independent technology judgment | `market/capability-map.md`, `final-project/technology-decisions.md` | PASS |
| FR-007 4–6 business-distinct candidates | `candidates/portfolio.md` | PASS — 6 |
| FR-008 candidate task/tools/system/failure/eval/scope | `candidates/portfolio.md` | PASS |
| FR-009 fixed six-dimension weights | `candidates/scoring-rubric.md`, `candidates/scoring.csv` | PASS |
| FR-010 1–10 scores + rationale/recomputability | `candidates/scoring.csv`, `candidate-evidence-matrix.md` | PASS |
| FR-011 first recommendation and switch evidence | `candidates/first-recommendation.md` | PASS |
| FR-012 three-role red team | `decisions/red-team-*.md` | PASS |
| FR-013 rescore/switch/delete/downgrade allowed | `decisions/red-team-resolution.md`, `red-team-rescore.md` | PASS |
| FR-014 A–Q complete | `final-project/specification-a-q.md` | PASS |
| FR-015 5–10 complete scenarios | `final-project/scenarios.md` | PASS — 10 |
| FR-016 required failure/safety scenarios | `scenarios.md`, `architecture-reliability-security.md` | PASS |
| FR-017 architecture responsibility separation | `architecture-reliability-security.md`, `specification-a-q.md` | PASS |
| FR-018 technology enterprise/project/learning value + priority | `technology-decisions.md` | PASS |
| FR-019 independent judgment for Python/Java/orchestration/frontend/MCP/RAG/storage/retrieval/obs/container/K8s/Multi-Agent | `technology-decisions.md` | PASS |
| FR-020 Agent state/steps/conditions/tool loop/stop/retry/checkpoint/memory/HITL | `architecture-reliability-security.md` | PASS |
| FR-021 complete tool semantics | `tool-contracts.md` | PASS — 8 |
| FR-022 RAG only when justified + corpus/retrieval/citation/eval | `specification-a-q.md` G, `evaluation-design.md` | PASS |
| FR-023 business backend has real domain logic | `specification-a-q.md` H, `architecture-reliability-security.md` | PASS |
| FR-024 business + Agent/audit data relationships | `architecture-reliability-security.md` | PASS |
| FR-025 50–100 eval cases + required metrics | `evaluation-design.md` | PASS — 60 planned |
| FR-026 Baseline/V1/Optimized comparable design | `evaluation-design.md` | PASS |
| FR-027 reconstructable Agent run | `architecture-reliability-security.md` observability | PASS |
| FR-028 unit/API/tool/Agent/eval/failure tests | `specification-a-q.md` L, `architecture-reliability-security.md` | PASS |
| FR-029 injection/auth/validation/sensitive data/write isolation/approval/audit/least privilege | `architecture-reliability-security.md` | PASS |
| FR-030 simple reproducible deployment and explicit K8s judgment | `technology-decisions.md`, `specification-a-q.md` M | PASS |
| FR-031 6–8 week runnable roadmap; Week-2 slice | `weekly-roadmap.md` | PASS |
| FR-032 interview mapping and personal reproduction boundary | `interview-map.md` | PASS |
| FR-033 resume/README/demo and no fake metrics | `career/resume-template-cn.md`, `readme-demo-plan.md`, `evidence-backed-resume-claims.md` | PASS |
| FR-034 fact/inference/recommendation/assumption/target distinction + sources | `evidence-ledger.md`, market artifacts | PASS at design/execution-artifact level |
| FR-035 prioritize execution/reliability/safety/eval/obs; cut UI/CRUD/infra | `scope-cut-plan.md`, `technology-decisions.md` | PASS |

## Success criteria

| Criterion | Evidence | Status |
|---|---|---|
| SC-001 >=30 dedup jobs; >=60% early-career; traceable capability claims | `sample-composition.md`, `source-audit.md`, `capability-map.md` | PASS — 30 / 20 employers / 20% audit |
| SC-002 4–6 candidates with six scores/weights | `portfolio.md`, `scoring.csv` | PASS — 6 |
| SC-003 first recommendation red-teamed; fatal risks dispositioned | `red-team-resolution.md`, `red-team-rescore.md` | PASS |
| SC-004 A–Q 100%; understandable business/Agent/core scope | `specification-a-q.md`, `spec-gate-report.md` | PASS at design level |
| SC-005 5–10 scenarios + 8 key failure/safety classes | `scenarios.md` | PASS — 10 |
| SC-006 all important technology candidates have value/ROI/priority | `technology-decisions.md` | PASS |
| SC-007 50–100 eval schema + 10 metrics + 3-version experiment | `evaluation-design.md` | PASS — 60 planned |
| SC-008 runnable weekly outputs + Week-2 vertical slice | `weekly-roadmap.md`, `implementation-plan-gate-report.md` | PASS at plan level |
| SC-009 interview map for Must modules | `interview-map.md` | PASS |
| SC-010 all numeric career outcomes require real eval evidence | `evidence-backed-resume-claims.md` | PASS — all result claims currently target |
| SC-011 reviewer can classify core/deferred/not-do scope | `specification-a-q.md`, `scope-cut-plan.md`, `technology-decisions.md` | PASS at design level |

## Traceability conclusion

All FR-001–FR-035 and SC-001–SC-011 have a concrete artifact. Criteria that inherently require implemented software or measured runs are explicitly marked as design/plan-level and are not misrepresented as implementation results.
