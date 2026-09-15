# Feature Specification: CommerceAgent 企业电商售后执行与异常处置 Agent

**Feature Branch**: `[002-commerce-after-sales-agent]`

**Created**: 2026-09-15

**Status**: Draft

**Input**: Build an enterprise e-commerce after-sales execution and exception-handling Agent that can understand ambiguous customer requests, gather evidence across order/logistics/policy systems, dynamically choose the next business tool or path, execute only authorized after-sales actions, escalate high-risk/uncertain cases, and produce auditable results. It must not be a FAQ chatbot or a fixed intent-to-refund router.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 物流异常退款闭环 (Priority: P1)

消费者提出“订单一直没收到，我不要了，帮我退款”之类的自然语言请求。系统必须识别相关订单，检查订单与物流状态，在需要时获取售后规则，并通过确定性资格检查判断是否允许退款；满足条件时创建退款申请并验证最终业务状态。

**Why this priority**: 这是最小可用业务闭环，能够同时证明自然语言理解、动态取证、Tool Calling、确定性业务规则、安全写入和最终状态验证。

**Independent Test**: 给定一个 `SHIPPED`、未签收、物流超过阈值无更新且普通金额的订单，用户只提供自然语言投诉；系统应独立完成订单定位、物流查询、资格检查、退款创建和写后验证，并且只能生成一个退款申请。

**Acceptance Scenarios**:

1. **Given** 用户拥有一个已发货但 120 小时无有效物流更新的订单且后端资格服务返回可退款，**When** 用户请求退款，**Then** 系统创建且仅创建一个正确金额的退款申请，并返回可验证的退款编号与处理结果。
2. **Given** 退款创建调用发生超时且结果未知，**When** Agent 恢复流程，**Then** 系统必须先查询售后状态并使用同一逻辑幂等标识处理，不得产生重复退款申请。

---

### User Story 2 - 已签收商品改走退货路径 (Priority: P1)

当订单已经签收时，系统必须根据新的业务证据改变处理路径，而不是继续执行未签收退款。

**Why this priority**: 该故事直接验证“中间 Tool Result 会改变下一步动作”，是 Agent Value Gate 的核心证明。

**Independent Test**: 将同一类用户请求放到已签收且仍在退货期的订单上，系统应从退款路径切换到退货/退货退款路径。

**Acceptance Scenarios**:

1. **Given** 订单已签收 3 天且退货资格允许，**When** 用户说“直接给我退款”，**Then** 系统不得直接创建未签收退款，而应进入退货资格检查并创建退货申请。

---

### User Story 3 - 模糊订单澄清 (Priority: P1)

当用户说“把上次买的耳机退掉”但账号中存在多个候选订单时，系统必须先澄清订单身份。

**Why this priority**: 企业级 Agent 不能通过猜测关键业务对象来完成资金或状态写入。

**Independent Test**: 给定两个都可能匹配自然语言描述的订单，系统必须返回澄清问题且在用户确认前保持所有退款/退货写入计数为 0。

**Acceptance Scenarios**:

1. **Given** 当前用户存在两个相似耳机订单，**When** 用户发起模糊退货请求，**Then** 系统要求用户确认目标订单且不得提前产生任何售后写操作。

---

### User Story 4 - 高风险售后人工审批 (Priority: P2)

当确定性风险规则要求人工审批时，系统必须暂停自动执行并等待授权。

**Why this priority**: 高风险写操作的 Human-in-the-loop 是企业 Agent 与普通自动化脚本的重要区别。

**Independent Test**: 给定一个满足售后资格但金额达到高风险阈值的订单，Agent 只能创建审批请求并进入等待状态；审批通过前退款/退货写操作必须为 0。

**Acceptance Scenarios**:

1. **Given** 资格服务返回 `approval_required=true`，**When** Agent 准备执行售后动作，**Then** 系统进入 `WAITING_APPROVAL`，只有合法审批结果到达后才允许继续。

---

### User Story 5 - 无法自动处理时安全转人工 (Priority: P2)

当关键证据缺失、业务状态冲突、规则无法自动决策或依赖服务持续失败时，系统必须安全停止自动写入并转人工。

**Why this priority**: 企业系统必须优先保证安全，而不是为了“完成任务”而猜测业务状态。

**Independent Test**: 关闭物流服务或让资格服务返回 `MANUAL_REVIEW`，系统不得凭模型推断继续退款，而应创建人工工单或清晰返回需要人工介入的状态。

**Acceptance Scenarios**:

1. **Given** 物流状态无法在重试预算内获取，**When** 用户要求基于“疑似物流丢失”退款，**Then** 系统不得生成未经证据支持的退款，并应转人工或返回证据不足状态。
2. **Given** 资格服务返回 `MANUAL_REVIEW`，**When** Agent 处理请求，**Then** 系统创建可追踪的售后工单并附带已收集证据。

---

### User Story 6 - 售后规则检索与可解释结果 (Priority: P2)

系统可以检索非结构化售后政策，用于解释处理依据和补充上下文，但政策文本本身不能直接授权资金或业务写入。

**Why this priority**: 该故事把 RAG 的合理边界与确定性业务规则分离，避免“向量库即业务数据库”。

**Independent Test**: 给定一个需要政策解释的售后案例，系统应返回有效政策来源/版本信息；即使检索文本声称“可直接退款”，最终售后资格仍必须来自确定性业务服务。

**Acceptance Scenarios**:

1. **Given** 检索结果包含适用售后条款，**When** 系统解释处理结果，**Then** 返回可追溯政策来源，同时最终资格与金额与确定性服务保持一致。
2. **Given** 检索到相互冲突或过期政策，**When** 无法确定有效版本，**Then** 系统不得选择任意文本作为授权依据，而应安全停止或转人工。

---

### Edge Cases

- 用户存在多个同类订单且自然语言无法唯一指向目标订单。
- 用户输入不存在或不属于本人的订单号。
- 订单已取消、已经有退款/退货申请或处于不可重复售后状态。
- 物流服务超时、返回冲突状态或数据长期不可用。
- 售后政策检索无结果、命中过期版本或出现冲突版本。
- 资格服务不可用、返回拒绝或 `MANUAL_REVIEW`。
- 退款/退货写操作超时且是否成功未知。
- 用户重复提交同一个售后请求。
- 用户通过 Prompt Injection 声称管理员权限或要求跳过规则。
- 高金额或异常商品需要人工审批。
- Agent 达到最大步骤数、重复调用同一 Tool 而没有获得新证据。
- 写操作成功但最终状态验证失败。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept natural-language after-sales requests and classify the requested business goal without assuming a final action prematurely.
- **FR-002**: System MUST resolve the target order only from orders accessible to the authenticated user.
- **FR-003**: System MUST ask for clarification when multiple plausible orders remain and MUST NOT perform a business write before order resolution.
- **FR-004**: System MUST maintain explicit task state across multi-step after-sales handling.
- **FR-005**: System MUST choose the next allowed business capability based on current evidence rather than using one fixed path for all refund-like requests.
- **FR-006**: Different order/logistics/eligibility evidence MUST be able to produce materially different outcomes including clarification, refund, return, approval, escalation, denial, or safe stop.
- **FR-007**: System MUST enforce a maximum step budget and stop conditions that prevent infinite tool loops.
- **FR-008**: System MUST validate tool results and error states before using them as business evidence.
- **FR-009**: System MUST obtain refund/return eligibility, maximum allowed amount, and approval requirements from deterministic business rules rather than from model output or retrieved prose.
- **FR-010**: System MUST NOT allow the Agent to override eligibility, amount, ownership, approval, or legal state-transition results.
- **FR-011**: System MUST support read capabilities for user orders, order detail, logistics state, after-sales status, and applicable policy knowledge.
- **FR-012**: System MUST support guarded business writes for refund request, return request, support ticket, and approval request where applicable.
- **FR-013**: Every money/state-changing write MUST be authorized and validated server-side against current business state.
- **FR-014**: Every logical refund/return write MUST be idempotent and MUST NOT create duplicates during user retry, Agent retry, or ambiguous network timeout.
- **FR-015**: After a write attempt, system MUST verify resulting business state before claiming success to the user.
- **FR-016**: System MUST pause high-risk actions when an authoritative risk rule requires human approval.
- **FR-017**: The Agent MUST NOT be able to self-approve, fabricate approval state, or bypass an approval requirement through prompt text.
- **FR-018**: System MUST provide a safe escalation path that can create a support ticket with already-collected evidence when automatic processing cannot continue.
- **FR-019**: Unstructured policy retrieval MAY be used for after-sales policy/SOP context and explanation.
- **FR-020**: Policy retrieval MUST preserve source/version/effective metadata sufficient for citation and conflict handling.
- **FR-021**: Retrieved text MUST be treated as untrusted data and MUST NOT change authorization, tool allowlists, approval thresholds, refund amount, or deterministic eligibility rules.
- **FR-022**: User-provided claims such as “I am an administrator” MUST NOT change the authenticated principal or business permission.
- **FR-023**: System MUST prevent a user from reading or modifying another user's order or after-sales state.
- **FR-024**: System MUST expose only registered, allowlisted business capabilities to the Agent and MUST NOT accept arbitrary internal endpoint, URL, SQL, or service names from model output.
- **FR-025**: System MUST record a unique run identifier for each Agent execution.
- **FR-026**: System MUST record structured state transitions, tool name, validated parameter summary, result/error, retry/timeout events, approval state, write result, and final verification result for each run.
- **FR-027**: System MUST make one failed run reconstructable from structured trace data without requiring hidden chain-of-thought.
- **FR-028**: System MUST support resettable synthetic business states for offline evaluation so expected tool/actions and final state can be checked reproducibly.
- **FR-029**: System MUST maintain a versioned offline evaluation dataset of at least 60 cases and target approximately 74 cases across normal, branching, failure, safety, approval, idempotency, and retrieval scenarios.
- **FR-030**: Evaluation MUST measure at minimum task success, tool selection, parameter correctness, business-state correctness, policy compliance, unsafe actions, duplicate writes, average tool calls, end-to-end latency, and token usage; retrieval/citation metrics MUST be included for policy-retrieval cases.
- **FR-031**: Baseline and Agent versions MUST be evaluated on comparable dataset versions, tool permissions, reset states, and metric definitions.
- **FR-032**: The product scope MUST remain limited to after-sales execution for the first releasable version and MUST exclude broad pre-sales recommendation, merchant marketing, procurement, generic omnichannel customer service, and model-training functionality.

### Key Entities *(include if feature involves data)*

- **User**: Authenticated actor allowed to access only their own commerce and after-sales data.
- **Order**: Authoritative purchase record including current fulfilment/after-sales state and ownership.
- **OrderItem**: Product/category information required for after-sales rule evaluation.
- **Shipment / LogisticsEvent**: Delivery state and event history used as evidence for logistics-related cases.
- **AfterSalesPolicy**: Versioned unstructured policy/SOP content used for retrieval and explanation.
- **EligibilityDecision**: Deterministic result describing allowed action, maximum amount, approval requirement, policy/reason code, and denial/manual-review state.
- **RefundRequest**: Idempotent refund business object with lifecycle state.
- **ReturnRequest**: Idempotent return/return-refund business object with lifecycle state.
- **SupportTicket**: Escalation object containing evidence and reason for human handling.
- **ApprovalRequest**: Human-in-the-loop state for configured high-risk actions.
- **AgentRun**: One user task execution with explicit state and final outcome.
- **ToolExecution**: Structured record of one allowed business capability invocation.
- **AuditLog**: Immutable-enough business/security audit event associated with important reads/writes and decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can independently demonstrate at least five business paths: logistics-anomaly refund, delivered-item return, ambiguous-order clarification, high-risk approval, and safe escalation.
- **SC-002**: At least four seeded business states for the same refund-like natural-language request produce at least three materially different next actions or tool paths.
- **SC-003**: 100% of money/state-changing evaluation cases use deterministic eligibility/authorization before the write is accepted.
- **SC-004**: In the final safety evaluation set, no unauthorized cross-user write or approval-bypassing write is accepted by the business system.
- **SC-005**: In duplicate/retry/ambiguous-timeout evaluation cases, each logical refund or return produces at most one corresponding business write.
- **SC-006**: 100% of completed Agent runs include enough structured trace information to reconstruct the main state/tool/approval/write/verification path.
- **SC-007**: The project includes a versioned offline evaluation set with at least 60 cases and a target of approximately 74 cases, with a frozen test split used for final reporting.
- **SC-008**: Baseline and final Agent results reported in project materials are produced from comparable evaluation conditions and linked to dataset/run configuration.
- **SC-009**: A 60–90 second demo can show one normal after-sales execution plus one safety/failure path and visibly prove that the system changes business state or deliberately refuses/escalates rather than merely answering a question.
- **SC-010**: No resume/README performance percentage, latency claim, safety result, or improvement number is presented as achieved unless backed by a reproducible evaluation run and metric definition.

## Assumptions

- The first implementation uses synthetic/local but contract-realistic e-commerce business systems; no claim of real production payment/e-commerce integration is required.
- The v1 user is already authenticated; building a complete login/account system is outside the core feature.
- The v1 focuses on one bounded after-sales domain: order identification, logistics evidence, refund/return eligibility, refund/return request creation, escalation, and one human-approval path.
- Product recommendation, pre-sales FAQ, merchant operations, marketing, procurement, real payment settlement, omnichannel support, model training, and multi-agent collaboration are out of scope for v1.
- If implementation evidence shows that the workflow reduces to a fixed `intent → refund endpoint` router and intermediate evidence does not change the next action, the feature has failed its Agent-value hypothesis and must be redesigned before adding more technology.