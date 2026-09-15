# Tasks: 求职导向的 Agent 项目决策与设计

**Input**: Design documents from `specs/001-agent-career-project/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/artifact-contracts.md`, `quickstart.md`

**Tests**: 本 feature 不实现最终 Agent 应用，因此不生成代码级 TDD 任务；独立验收通过来源抽查、去重检查、评分重算、阶段门检查、规格覆盖检查、交叉引用检查和 quickstart 验证完成。

**Organization**: 任务按 User Story 组织。虽然 US1～US3 均为 P1，但 FR-001 与 Contract 1～5 明确要求阶段门顺序，因此本 feature 有意采用“证据 → 候选 → 反证 → 最终规格 → 路线 → 求职材料”的串行主链；阶段内部仍标记可并行任务。

**Scope boundary**: 本任务清单只执行招聘研究、项目决策与最终项目设计；不得创建 Java/Python/前端/数据库/Agent Framework 等最终应用实现代码。最终 Agent 应用必须在选题和 A～Q 规格通过后另建 implementation feature。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可与同阶段其他标记任务并行，且不会写同一文件或依赖未完成输出
- **[Story]**: 对应 `spec.md` 中的 User Story
- 所有任务必须写入明确文件路径，并保留事实、推断、建议、假设和待验证目标的区分

---

## Phase 1: Setup（研究与决策产物结构）

**Purpose**: 建立本 feature 的执行产物目录和审计入口，不初始化任何应用代码或技术栈。

- [ ] T001 Create the execution artifact index, directory map, source-of-truth rules, and status table in `specs/001-agent-career-project/artifacts/README.md`
- [ ] T002 [P] Create an evidence ledger template that records claim type (fact/inference/recommendation/assumption/target), source URL, access date, source tier, evidence strength, and notes in `specs/001-agent-career-project/artifacts/evidence-ledger.md`
- [ ] T003 [P] Create a decision ledger template with `decision_id`, stage, question, decision, evidence refs, rationale, alternatives, uncertainty, revisit trigger, and status in `specs/001-agent-career-project/artifacts/decisions/decision-log.md`

**Checkpoint**: 研究、评分、反证和最终规格都有明确的版本化落点；未创建最终应用代码目录。

---

## Phase 2: Foundational（所有 User Story 的阻塞前置）

**Purpose**: 把 `research.md`、`data-model.md` 和 contracts 中已经确定的方法转换成可执行协议，避免后续边做边改规则。

**⚠️ CRITICAL**: 本阶段完成前不得开始岗位统计或候选评分。

- [ ] T004 Reconcile the source-tier mismatch between `research.md` (A–D) and `data-model.md` (A/B/C) by defining an explicit operational mapping, inclusion/exclusion rules, early-career scope, employer caps, dedupe key, alias handling, and page-failure policy in `specs/001-agent-career-project/artifacts/market/collection-protocol.md`; do not modify the source design files
- [ ] T005 [P] Materialize the fixed 25/20/20/15/10/10 weights, 1/3/5/7/9 anchors, evidence grades, defensible score intervals, six fatal gates, and the `<0.5 or overlapping range` validation trigger in `specs/001-agent-career-project/artifacts/candidates/scoring-rubric.md`
- [ ] T006 [P] Create the three-role red-team template with role, challenge, severity P0/P1/P2, evidence, failure scenario, alternative candidate, proposed deletion/downgrade, validation method, disposition, and `old score → risk → action → new score` fields in `specs/001-agent-career-project/artifacts/decisions/red-team-template.md`
- [ ] T007 [P] Create the A–Q coverage checklist, 5–10 scenario requirement, tool-risk requirements, technology three-question test, 50–100 evaluation-case requirement, reliability/security coverage, and Must/Should/Nice/Reject rules in `specs/001-agent-career-project/artifacts/final-project/specification-checklist.md`
- [ ] T008 Consolidate Contract 1–5 inputs, required outputs, exit gates, FR-001 stage ordering, and the rule that no final project or tech stack may be frozen early in `specs/001-agent-career-project/artifacts/stage-gates.md`

**Checkpoint**: Foundation ready. Rules are frozen before evidence collection and scoring begin.

---

## Phase 3: User Story 1 - 用招聘证据建立能力地图 (Priority: P1) 🎯 MVP

**Goal**: 形成至少 30 条可追溯、去重的目标岗位核心样本和一份按职责语境归纳的能力地图。

**Independent Test**: 仅使用本阶段的岗位样本、来源、排除/去重记录和能力地图，第三方能够抽查样本并复核主要能力结论；核心结论必须能追溯到岗位或明确标注为推断。

### Implementation for User Story 1

- [ ] T009 [P] [US1] Collect the first core batch of at least 15 2026 early-career Agent/LLM application engineering postings from at least 4 employers, recording all `Job Posting Sample` fields and direct source URLs in `specs/001-agent-career-project/artifacts/market/job-postings-batch-a.csv`
- [ ] T010 [P] [US1] Collect a second core batch of at least 15 2026 early-career Agent/LLM application engineering postings from at least 4 employers, prioritizing employers or channels not represented in batch A, and record all `Job Posting Sample` fields in `specs/001-agent-career-project/artifacts/market/job-postings-batch-b.csv`
- [ ] T011 [P] [US1] Collect a separate production/senior trend reference set without mixing it into the early-career denominator, recording why each record is reference-only in `specs/001-agent-career-project/artifacts/market/trend-reference.csv`
- [ ] T012 [US1] Normalize, classify, merge, and deduplicate batches into `specs/001-agent-career-project/artifacts/market/job-postings.csv`; populate every required `Job Posting Sample` field, use the source-tier mapping from `collection-protocol.md`, enforce “相同 `dedupe_key` 只保留一条主记录”, keep alias URLs as notes, and keep senior trend samples outside the core denominator
- [ ] T013 [US1] Record excluded pure pretraining/RLHF/CUDA/research roles, invalid or inaccessible sources, duplicate postings, and exclusion reasons in `specs/001-agent-career-project/artifacts/market/exclusions.csv`; ensure records that are “仅包含模型训练、CUDA、RLHF 或论文研究职责” are explicitly excluded from the core sample
- [ ] T014 [US1] Verify sample composition against SC-001 and research constraints—at least 30 deduplicated core postings, at least 8 independent employers, no more than 5 core records per employer, and at least 60% internship/campus/0–2 year roles—and record counts, denominator definitions, and any shortfall in `specs/001-agent-career-project/artifacts/market/sample-composition.md`
- [ ] T015 [US1] Randomly audit at least 20% of the core sample for title, employer, career level, responsibilities, must-have/preferred coding, source accessibility, and dedupe correctness, recording pass/fail and corrections in `specs/001-agent-career-project/artifacts/market/source-audit.md`
- [ ] T016 [US1] Derive `Capability Signal` records from the audited core sample, including `evidence_job_ids`, `must_count`, `preferred_count`, `responsibility_count`, role distribution, context summary, confidence, learning priority, and caveat in `specs/001-agent-career-project/artifacts/market/capability-signals.csv`; separate framework names from underlying capabilities and do not use keyword frequency alone
- [ ] T017 [US1] Write the evidence-backed capability map, job-family/company-type differences, high-frequency-but-low-ROI caveats, evidence-strength labels, and a Contract 1 / SC-001 exit-gate verdict in `specs/001-agent-career-project/artifacts/market/capability-map.md`

**Checkpoint**: Contract 1 must PASS before US2 scoring can begin. If it fails, add/repair evidence rather than proceeding with a provisional recommendation.

---

## Phase 4: User Story 2 - 比较并选择可完成的项目方向 (Priority: P1)

**Goal**: 基于已通过 Contract 1 的能力地图生成 4～6 个企业业务方向候选，先过 Fatal Gates，再按固定六维模型评分并形成可辩护的第一推荐。

**Independent Test**: 评审者能够仅依据候选资料和固定权重重算每个候选总分，并验证首选没有用高分掩盖致命风险。

### Implementation for User Story 2

- [ ] T018 [US2] Generate 4–6 business-distinct `Project Candidate` entries from the passed capability map in `specs/001-agent-career-project/artifacts/candidates/portfolio.md`, and for each include business problem, target users, business system, agent necessity, observable state-changing action, core vertical slice, evaluation feasibility, 6–8 week scope, fatal risks, role mapping, and why it is not just chat/PDF QA
- [ ] T019 [P] [US2] Map every candidate to supporting job IDs, capability signals, target company types, target role families, contradictory evidence, and evidence gaps in `specs/001-agent-career-project/artifacts/candidates/candidate-evidence-matrix.md`
- [ ] T020 [US2] Apply all six non-compensatory fatal gates to every candidate and record pass/reject/needs-validation, evidence, and the smallest possible validation action in `specs/001-agent-career-project/artifacts/candidates/fatal-gates.md`; a failed gate must not be compensated by a high weighted score
- [ ] T021 [US2] Score only gate-eligible candidates on demand match 25%, Agent depth 20%, interview value 20%, eight-week feasibility 15%, background fit 10%, and differentiation 10%, recording 1–10 center score, anchor-based rationale, evidence grade, defensible interval, supporting refs, change trigger, and weighted low/center/high total in `specs/001-agent-career-project/artifacts/candidates/scoring.csv`
- [ ] T022 [P] [US2] Recalculate ranking sensitivity under plausible ±1 point changes to each scoring dimension, identify dimensions capable of changing the ranking, and document uncertainty without hiding overlap in `specs/001-agent-career-project/artifacts/candidates/sensitivity-analysis.md`
- [ ] T023 [US2] Check whether Top 1 vs Top 2 center-score gap is `<0.5` or weighted intervals materially overlap; if triggered, execute one 4–8 hour low-cost validation (for example data/API feasibility, thin tool loop, 10–15 labeled eval cases, or JD mapping check) and rescore; otherwise record why no validation is required in `specs/001-agent-career-project/artifacts/candidates/tie-break-validation.md`
- [ ] T024 [US2] Produce the first recommendation with candidate name, target company/role mapping, strongest evidence, MVP vertical slice, maximum delivery risk, range-reduction strategy, uncertainty, and explicit evidence that would change the recommendation in `specs/001-agent-career-project/artifacts/candidates/first-recommendation.md`
- [ ] T025 [US2] Verify Contract 2 and SC-002 against the candidate portfolio, fatal gates, score reproducibility, sensitivity analysis, and tie-break rule, recording PASS/FAIL plus remediation in `specs/001-agent-career-project/artifacts/candidates/candidate-gate-report.md`

**Checkpoint**: Contract 2 must PASS before the first recommendation is treated as eligible for red-team review.

---

## Phase 5: User Story 3 - 从三个角色反证首选方案 (Priority: P1)

**Goal**: 独立攻击第一推荐，消除伪需求、教程复刻、技术堆砌和不可交付范围；允许最终改选。

**Independent Test**: 只阅读三份独立反证和处置记录，评审者能够看到每条严重挑战如何导致接受风险、增加验证、降级、删除或改选，并能追踪评分变化。

### Implementation for User Story 3

- [ ] T026 [P] [US3] Write an interviewer elimination memo that attacks tutorial resemblance, Agent necessity, depth under follow-up questioning, metric credibility, and which core mechanisms the user must be able to reimplement in `specs/001-agent-career-project/artifacts/decisions/red-team-interviewer.md`
- [ ] T027 [P] [US3] Write a hiring-manager elimination memo that attacks 30–60 second business clarity, mapping to real team responsibilities, onboarding signal, business value, and whether a more common enterprise problem would produce stronger hiring evidence in `specs/001-agent-career-project/artifacts/decisions/red-team-hiring-manager.md`
- [ ] T028 [P] [US3] Write a developer elimination memo that attacks data availability, integration realism, tool failure, duplicate calls, permissions, prompt injection, cost/latency, debugging, observability, and 6–8 week feasibility in `specs/001-agent-career-project/artifacts/decisions/red-team-developer.md`
- [ ] T029 [US3] Consolidate every red-team issue with P0/P1/P2 severity, evidence, failure scenario, alternative candidate, proposed cut/validation, disposition (`accept risk` / `validate` / `downgrade` / `delete` / `switch`), owner, and `old score → risk → action → new score` in `specs/001-agent-career-project/artifacts/decisions/red-team-resolution.md`
- [ ] T030 [US3] Re-run fatal gates and conservative scoring after all dispositions, compare the revised first recommendation against the strongest alternative, and record whether any P0 remains or the lead survives without scope expansion in `specs/001-agent-career-project/artifacts/decisions/red-team-rescore.md`
- [ ] T031 [US3] Freeze the final project choice only after Contract 3 passes, recording selected candidate, rejected alternatives, scope deletions/downgrades, residual risks, revisit triggers, and whether the recommendation changed in `specs/001-agent-career-project/artifacts/decisions/final-selection.md`

**Checkpoint**: Contract 3 must PASS. No final technology stack or A–Q project specification may be frozen before T031.

---

## Phase 6: User Story 4 - 形成技术中立的完整项目规格 (Priority: P2)

**Goal**: 为经过反证的最终候选生成 A～Q 权威项目规格，明确 Agent 与确定性程序边界、业务状态变化、失败恢复、安全、评估和可观测性。

**Independent Test**: 使用 A～Q 清单和 Contract 4 独立审查，能够在 15 分钟内理解业务问题、Agent 必要性、核心闭环和两个月范围；所有 Must 技术均通过三问且不存在炫技组件。

### Implementation for User Story 4

- [ ] T032 [US4] Create the authoritative A–Q project specification shell and fill business positioning, users, scope boundary, selected-candidate evidence, main workflow, deterministic-vs-Agent responsibility boundary, and cross-reference placeholders in `specs/001-agent-career-project/artifacts/final-project/specification-a-q.md`
- [ ] T033 [P] [US4] Define 5–10 `Agent Scenario` records with user input, Agent decision, business data, tool sequence, retrieval need, approval rule, expected output, failure modes, and acceptance oracle in `specs/001-agent-career-project/artifacts/final-project/scenarios.md`; the set must cover timeout/retry, wrong tool, duplicate call/idempotency, prompt injection, unauthorized action, high-risk approval, parameter error, and partial failure
- [ ] T034 [P] [US4] Define every `Tool Contract` with name, business function, input/output schema, read/write property, risk level, automatic-call permission, authorization, approval, timeout, retry, idempotency key, error types, audit fields, and prohibited behavior in `specs/001-agent-career-project/artifacts/final-project/tool-contracts.md`; all write tools must require business-system-side validation rather than prompt-only protection
- [ ] T035 [P] [US4] Evaluate Python, Java, Agent orchestration, frontend, MCP/tool protocol, RAG, structured storage, retrieval, observability, containerization, cloud deployment, cluster orchestration, and Multi-Agent independently in `specs/001-agent-career-project/artifacts/final-project/technology-decisions.md`, answering enterprise value, project necessity, two-month learning ROI, complexity cost, Must/Should/Nice/Reject priority, and revisit trigger for each
- [ ] T036 [P] [US4] Design the versioned 50–100 case evaluation set and metric formulas in `specs/001-agent-career-project/artifacts/final-project/evaluation-design.md`, using the `Evaluation Case` fields `case_id`, `dataset_split` (`dev`/`test`), category, user task, resettable initial state, allowed tools, expected calls/predicates, forbidden actions, expected business state, expected answer facts, citation expectation, scorers, and tags; define task success, tool selection, parameter accuracy, policy compliance, unsafe action, retrieval recall, citation accuracy, average tool calls, end-to-end latency, and Token cost plus Baseline/V1/Optimized comparability and leakage controls
- [ ] T037 [P] [US4] Define UI, Agent service, deterministic business backend, business database, retrieval, cache, tool protocol, observability, evaluation, state/checkpoints, stop/max-step conditions, retries, Human-in-the-loop, least privilege, parameter validation, injection defense, read/write isolation, audit, and idempotency boundaries in `specs/001-agent-career-project/artifacts/final-project/architecture-reliability-security.md`; include only layers justified by the selected project
- [ ] T038 [US4] Integrate and cross-reference `scenarios.md`, `tool-contracts.md`, `technology-decisions.md`, `evaluation-design.md`, and `architecture-reliability-security.md` into all A–Q sections, resolving contradictions and explicitly marking Must/Should/Nice/Reject scope in `specs/001-agent-career-project/artifacts/final-project/specification-a-q.md`
- [ ] T039 [US4] Validate Contract 4, SC-004～SC-007, 100% A–Q coverage, 5–10 scenario coverage, all Must technology three-question answers, and absence of ornamental services/databases/Agents/frameworks, recording PASS/FAIL and remediation in `specs/001-agent-career-project/artifacts/final-project/spec-gate-report.md`

**Checkpoint**: Contract 4 must PASS before a build roadmap is treated as implementation-ready.

---

## Phase 7: User Story 5 - 获得每周可运行的实施与学习路线 (Priority: P2)

**Goal**: 把最终规格转换成 6 周证据核心 + 2 周缓冲/包装路线，并明确本人必须理解和可简化复现的核心机制。

**Independent Test**: 随机抽取任意一周，均能找到可运行增量、演示路径、验收标准、学习目标、风险、预算和削减项；第 2 周前必须出现 `User → Agent → Tool → Business System → Result` 的正常和受控失败路径。

### Implementation for User Story 5

- [ ] T040 [US5] Create the 6+2 week roadmap in `specs/001-agent-career-project/artifacts/final-project/weekly-roadmap.md`, including weekly runnable deliverable, demo path, acceptance criteria, core knowledge to master, AI-assist boundary, time budget, dependencies, risks, and cut items; enforce Week 2 vertical slice, Week 3 reliability/security, Week 4 frozen evaluation, Week 5 one attributable optimization, Week 6 reproducible core, and optional Weeks 7–8
- [ ] T041 [P] [US5] Map every Must module and major design decision to likely interview questions, required conceptual explanations, core code/mechanism the user must be able to reproduce, work AI may assist with, and judgment that cannot be outsourced to AI in `specs/001-agent-career-project/artifacts/final-project/interview-map.md`
- [ ] T042 [P] [US5] Define the Must/Should/Nice/Reject cut order, Week 1 Must freeze, Week 2 no-new-Must rule, circuit breakers for schedule/model/API/cost risk, and which UI/integration/infrastructure items are cut before evaluation/safety/observability in `specs/001-agent-career-project/artifacts/final-project/scope-cut-plan.md`
- [ ] T043 [US5] Validate US5 acceptance criteria, SC-008～SC-009, and the implementation/interview portions of Contract 5, recording any blocked dependency or scope correction in `specs/001-agent-career-project/artifacts/final-project/implementation-plan-gate-report.md`

**Checkpoint**: The implementation route is ready for a separate implementation feature; this feature still does not create application code.

---

## Phase 8: User Story 6 - 生成诚实可验证的求职材料 (Priority: P3)

**Goal**: 生成可在项目实现后更新的中文求职材料模板；未实际测量的指标不得伪装成成果。

**Independent Test**: 对照证据账本抽查所有数字化表述，未运行的结果均为 target/placeholder；任何 measured/approved 数字都要求未来关联实际评估运行、数据集版本和指标定义。

### Implementation for User Story 6

- [ ] T044 [P] [US6] Create a Chinese project-experience and resume bullet template that describes problem, Agent execution loop, reliability/safety/evaluation work, and leaves all unmeasured percentages, latency, cost, success-rate, and sample-size claims as explicit targets/placeholders in `specs/001-agent-career-project/artifacts/career/resume-template-cn.md`
- [ ] T045 [P] [US6] Create the README structure and 60–90 second demo script, including architecture narrative, happy path, controlled failure, trace/eval evidence, setup reproducibility, known limitations, and honest synthetic/local-system boundaries in `specs/001-agent-career-project/artifacts/career/readme-demo-plan.md`
- [ ] T046 [US6] Create `Evidence-backed Resume Claim` records in `specs/001-agent-career-project/artifacts/career/evidence-backed-resume-claims.md`, enforcing `status = target / measured / approved`, requiring evaluation-run refs and dataset version for measured/approved numeric claims, requiring metric definition for numbers, limitations for every claim, and allowing only `approved` claims to be stated as achieved results; include the career-output portion of Contract 5 exit validation

**Checkpoint**: No fabricated outcome metric appears in career materials.

---

## Phase 9: Polish & Cross-Cutting Validation

**Purpose**: 验证整个研究—决策—规划闭环可以被第三方复核，并且没有跨阶段偷跑结论。

- [ ] T047 Build a requirement traceability matrix from FR-001～FR-035 and SC-001～SC-011 to concrete artifact paths, gate evidence, and current status in `specs/001-agent-career-project/artifacts/requirements-traceability.md`
- [ ] T048 Execute all seven validation scenarios in `specs/001-agent-career-project/quickstart.md` against the produced artifacts and record command/manual-check evidence, PASS/FAIL, and remediation in `specs/001-agent-career-project/artifacts/quickstart-validation.md`
- [ ] T049 Perform the final integrity audit for fact/inference/recommendation/assumption/target labeling, source access dates, dedupe denominators, score reproducibility, unresolved P0/P1 risks, unmeasured metrics, premature tech-stack freezing, synthetic-system disclosure, and accidental final-app coding scope; record the final go/no-go decision for creating a separate implementation feature in `specs/001-agent-career-project/artifacts/final-integrity-audit.md`

**Final Checkpoint**: Research and decision feature complete. Only after T049 PASS should a new implementation feature be created for the selected Agent application.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: no dependencies
- **Phase 2 — Foundational**: depends on Phase 1; blocks evidence collection and scoring
- **Phase 3 — US1**: depends on Phase 2; Contract 1 PASS blocks US2
- **Phase 4 — US2**: depends on US1 / Contract 1 PASS; Contract 2 PASS blocks US3
- **Phase 5 — US3**: depends on US2 / Contract 2 PASS; Contract 3 PASS blocks final project freeze
- **Phase 6 — US4**: depends on US3 / Contract 3 PASS; Contract 4 PASS blocks the implementation roadmap
- **Phase 7 — US5**: depends on US4 / Contract 4 PASS
- **Phase 8 — US6**: depends on final project specification and should follow US5 so career narratives match the frozen scope and roadmap
- **Phase 9 — Polish**: depends on all desired user stories and performs whole-feature closure

### User Story Dependency Graph

```text
Setup
  -> Foundational
  -> US1 Market Evidence + Capability Map
  -> US2 Candidate Portfolio + Fatal Gates + Scoring
  -> US3 Three-role Red Team + Final Selection
  -> US4 A–Q Final Project Specification
  -> US5 6+2 Week Implementation + Interview Roadmap
  -> US6 Honest Career Material Templates
  -> Final Traceability + Quickstart + Integrity Audit
```

This sequence is intentional and overrides the generic assumption that all user stories should start in parallel, because FR-001 and Contract 1–5 prohibit skipping stage gates.

### Within-Story Dependencies

- **US1**: T009/T010/T011 can run in parallel → T012 normalization/dedupe → T013/T014/T015 quality controls → T016 capability signals → T017 capability map/gate
- **US2**: T018 portfolio + T019 evidence matrix → T020 fatal gates → T021 scoring; T022 sensitivity may start once scoring exists → T023 tie validation → T024 recommendation → T025 gate report
- **US3**: T026/T027/T028 run independently in parallel → T029 resolution → T030 rescore → T031 final selection
- **US4**: T032 establishes master spec shell; T033/T034/T035/T036/T037 can proceed in parallel against the selected candidate → T038 integration → T039 gate
- **US5**: T040 roadmap; T041/T042 may run in parallel after the final specification exists → T043 gate
- **US6**: T044/T045 can run in parallel → T046 claim ledger and career-output validation

---

## Parallel Execution Examples

### User Story 1

```text
Parallel:
- T009 Collect core batch A
- T010 Collect core batch B
- T011 Collect trend-reference set

Then:
- T012 Normalize/merge/dedupe
```

### User Story 3

```text
Parallel:
- T026 Interviewer red team
- T027 Hiring-manager red team
- T028 Developer red team

Then:
- T029 Consolidate dispositions
- T030 Re-score
- T031 Freeze final selection
```

### User Story 4

```text
After T032 creates the master A–Q shell, run in parallel:
- T033 Agent scenarios
- T034 Tool contracts
- T035 Technology decisions
- T036 Evaluation design
- T037 Architecture/reliability/security

Then:
- T038 Integrate into A–Q
- T039 Contract 4 gate
```

---

## Implementation Strategy

### MVP First — User Story 1

1. Complete Phase 1 Setup
2. Complete Phase 2 Foundational rules
3. Execute US1 until Contract 1 passes
4. **STOP AND VALIDATE**: a third party must be able to reproduce the capability-map conclusions from the evidence pack

This is the smallest independently valuable increment: a defensible 2026 job-market capability map. It does **not** yet choose a project.

### Minimum Decision Loop — US1 + US2 + US3

1. Establish market evidence and capability map
2. Generate 4–6 candidates from evidence
3. Apply fatal gates before scoring
4. Run fixed-weight scoring + sensitivity analysis
5. Resolve close rankings through a low-cost validation
6. Attack the first recommendation from three independent roles
7. Freeze or switch the final project only after Contract 3 passes

At this point the question “what project should be built?” is resolved with an auditable decision trail.

### Full Feature Delivery

1. **US1** → evidence-backed capability map
2. **US2** → evidence-backed candidate ranking
3. **US3** → red-teamed final selection
4. **US4** → A–Q final project specification
5. **US5** → 6+2 week build/learning/interview roadmap
6. **US6** → honest career material templates
7. **Phase 9** → traceability, quickstart validation, integrity audit
8. Only then create a new implementation feature for actual application code

---

## Completion Summary

- **Total tasks**: 49
- **US1**: 9 tasks (T009–T017)
- **US2**: 8 tasks (T018–T025)
- **US3**: 6 tasks (T026–T031)
- **US4**: 8 tasks (T032–T039)
- **US5**: 4 tasks (T040–T043)
- **US6**: 3 tasks (T044–T046)
- **Setup/Foundation/Polish**: 11 tasks
- **Suggested MVP**: Setup + Foundational + US1, ending with a Contract 1 PASS capability map
- **Suggested minimum project-decision scope**: Setup + Foundational + US1 + US2 + US3
- **Format validation**: all executable tasks use `- [ ] Txxx [P?] [US?] Description with file path`; Setup/Foundation/Polish tasks intentionally omit story labels; story-phase tasks include `[USx]`
- **Application coding scope**: intentionally excluded from this feature; no Java/Python/frontend/database/Agent-framework implementation task is authorized here
