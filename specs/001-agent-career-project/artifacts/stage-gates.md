# Stage Gates

This file converts Contract 1–5 and FR-001 into an execution checklist.

## Gate 0 — Foundation ready
Required before evidence collection/scoring:
- collection protocol exists;
- scoring rubric exists;
- red-team template exists;
- final-spec checklist exists;
- source-tier mapping and stage ordering are explicit.

## Gate 1 — Market Evidence / Capability Map
Inputs: 2026 public job evidence.

PASS only if:
- at least 30 deduplicated core postings;
- at least 60% internship/campus/0–2-year early-career roles;
- at least 8 employers, max 5 core records per employer;
- all core records satisfy required Job Posting Sample fields;
- exclusions, dedupe rules, and source tiers are documented;
- at least 20% of core records are manually audited;
- capability conclusions preserve must/preferred/responsibility context and evidence strength;
- pure training/CUDA/RLHF/research and senior reference roles do not pollute the core denominator.

No candidate may be finally scored before Gate 1 PASS.

## Gate 2 — Candidate Portfolio
Inputs: Gate 1 capability map + user constraints.

PASS only if:
- 4–6 business-distinct candidates exist;
- each has a real business system, Agent necessity, observable state-changing action, evaluable vertical slice, 6–8 week scope, risks, and role mapping;
- all six fatal gates PASS or bounded validation has resolved uncertainty;
- six fixed weighted dimensions are fully scored and recomputable;
- score intervals, evidence grades, sensitivity analysis, and tie/overlap rule are disclosed.

No first recommendation may be treated as final before Gate 2 PASS.

## Gate 3 — Recommendation + Three-role Red Team
Inputs: Gate 2 candidate set.

PASS only if:
- interviewer, hiring-manager, and developer elimination memos are independent;
- every P0/P1/P2 issue has evidence and a disposition;
- every issue ends in accept risk / validate / downgrade / delete / switch;
- no unresolved P0 remains;
- revised fatal gates and conservative scoring are recorded;
- final selection may switch candidates and preserves an audit trail.

No final tech stack or A–Q specification may be frozen before Gate 3 PASS.

## Gate 4 — Final Project Specification
Inputs: Gate 3 selected candidate.

PASS only if:
- A–Q coverage is 100%;
- 5–10 scenarios cover happy path and required failures/security cases;
- every tool has risk/permission/retry/idempotency semantics;
- evaluation design covers 50–100 versioned cases and the required metrics;
- every important technology passes enterprise-value / project-necessity / learning-ROI scrutiny and is labeled Must/Should/Nice/Reject;
- Agent and deterministic business logic are explicitly separated;
- no ornamental service, database, Agent, framework, or infrastructure layer survives without evidence.

No implementation roadmap is considered build-ready before Gate 4 PASS.

## Gate 5 — Implementation / Interview / Career Plan
Inputs: Gate 4 final specification.

PASS only if:
- 6 core weeks + 2 optional/buffer weeks are defined;
- Week 2 includes a normal and controlled-failure `User → Agent → Tool → Business System → Result` slice;
- each week has runnable output, acceptance criteria, learning target, risk, budget, and cut item;
- Must modules map to interview questions and personally reproducible mechanisms;
- resume/README/demo outputs contain no unmeasured outcome stated as achieved.

## Final closure
After Gate 5, run requirement traceability, quickstart validation, and final integrity audit. Only a PASS should authorize creating a separate implementation feature for actual application code.
