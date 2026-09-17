# Tasks：CommerceAgent 企业电商售后执行与异常处置 Agent

**输入**：`specs/002-commerce-after-sales-agent/` 下的设计文档。  
**前置**：`spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`、`.specify/memory/constitution.md`。

任务按用户故事组织，每个增量都必须可独立验证。涉及高风险写入、Agent Value Gate、幂等、安全和离线 Eval 的测试不属于可选装饰。

格式：`[ID] [P?] [Story] 描述`

- `[P]`：可与同阶段其他不冲突任务并行。
- `[Story]`：对应 `spec.md` 用户故事。
- 每个实现任务都明确要修改的文件/目录。

---

## Phase 1：Setup

**目标**：只创建最小可运行项目骨架，不写业务功能。

- [ ] T001 创建 `commerce-backend/`、`agent-service/`、`web/`、`eval/`、`knowledge/policies/`、`infra/` 根目录，不创建无用微服务目录；创建并维护根 `README.md` 作为项目入口，只记录当前真实状态、设计入口、计划技术栈和第一实现目标，不提前填写未实测成果。
- [X] T002 使用 Spring Initializr 生成 `commerce-backend/`：Java 21、Maven、Spring Boot 4.1.1、group `com.seventeen17`、artifact/name `commerce-backend`、package `com.seventeen17.commerceagent`；依赖 Spring Web、Spring Security、Validation、Spring Data JPA、PostgreSQL Driver、Flyway Migration、Actuator、Testcontainers；保留 `mvnw`、`mvnw.cmd`、`.mvn/`。
- [X] T003 [P] 使用 `uv init --python 3.13` 初始化 `agent-service/`，加入 FastAPI、Uvicorn、LangGraph、Pydantic Settings、httpx、PostgreSQL/async DB、pytest、pytest-asyncio；依赖解析后提交 `uv.lock`。
- [X] T004 [P] 使用 Vite React + TypeScript 初始化 `web/`：`npm create vite@latest web -- --template react-ts`，保留 Vite/TS 基线配置。
- [X] T005 配置 PostgreSQL 与逻辑 schema（`commerce`、`agent`、`policy`、可选 `eval`）到 `infra/docker-compose.yml` 和 `.env.example`；设计独立 DB role，使 Agent Service 对 `commerce.*` 无直接权限。
- [ ] T006 [P] 在 `commerce-backend/pom.xml` 配置 Java format/static analysis/test 插件，在 `agent-service/pyproject.toml` 配置 Python lint/type-check。
- [ ] T007 [P] 配置 dev/test/eval：`commerce-backend/src/main/resources/application.yml`、`commerce-backend/src/test/resources/application-test.yml`、`agent-service/app/config/settings.py`。

**Checkpoint**：三端空壳可启动并连接本地 PostgreSQL；Java 21 / Python 3.13 / Docker 版本已验证；根 README 能准确反映当前阶段且不包含未实测成果。

---

## Phase 2：Foundational

**目标**：实现所有故事共用的安全、存储、Trace、Error 与 Agent State 基础。

- [ ] T008 创建初始 Flyway migration：`commerce.users`、`commerce.orders`、`commerce.order_items`、`commerce.shipments`、`commerce.logistics_events`、`commerce.after_sales_rules`、项目自有 `agent.agent_runs`、`agent.tool_executions`、`commerce.audit_logs`；文件 `commerce-backend/src/main/resources/db/migration/V001__core_schema.sql`。第三方 LangGraph checkpoint 表若由库自管理，放到独立 schema 并按 `research.md` 记录 migration 例外。
- [ ] T009 [P] 实现 User、Order、OrderItem、Shipment、LogisticsEvent JPA Entity/Repository：`commerce-backend/src/main/java/com/seventeen17/commerceagent/order/`、`logistics/`；保留 immutable ownership、optimistic `version`、权威价格/状态。
- [ ] T010 [P] 实现 `AfterSalesRule` 持久化：`eligibility/`；包含唯一 `rule_code`、version/effective dates、物流/退货/金额/审批阈值、`allowed_action`、`active`。
- [ ] T011 实现本地 JWT 认证和 role-aware principal：`security/`；Customer API 只能从 principal 推导 ownership。
- [ ] T012 [P] 实现与 `contracts/error-contracts.md` 对齐的统一 Error Envelope：`common/error/`。
- [ ] T013 [P] 实现结构化业务/安全 Audit Writer：`audit/`；禁止保存 hidden chain-of-thought 和 raw token。
- [ ] T014 创建 dev/eval fixture loader，预置 `customer-001`、`customer-002`、`approver-001`、订单/物流/规则，以及 `contracts/eval-internal-api.md` 的 reset endpoint；只能在 test/eval profile 注册。
- [ ] T015 [P] 定义显式 `AgentState`：`agent-service/app/agent/state.py`；包含 run id、principal context、intent、candidate/resolved order、evidence、eligibility、approval、tool history、step/retry budget、write/verification、terminal status。
- [ ] T016 [P] 实现类型化 Java API Client：`agent-service/app/clients/commerce_client.py`；负责 auth-context 传递、timeout、统一 response validation；token/principal 不能进入 model prompt。
- [ ] T017 实现持久化 Agent Run/Checkpoint/Structured Tool Trace：`agent-service/app/trace/`；支持 `RUNNING`、`WAITING_USER`、`WAITING_APPROVAL`、`COMPLETED`、`ESCALATED`、`FAILED`、`SAFE_STOP`。
- [ ] T018 实现 FastAPI JWT 验证、principal context、run ownership 与 run/status/event skeleton endpoint：`agent-service/app/security/`、`api/runs.py`、`main.py`；用户不得读取/恢复其他人的 run。

**Checkpoint**：已认证 synthetic state 与可恢复、owner-scoped AgentRun 能创建和追踪，但还不能执行退款/退货。

---

## Phase 3：US1 物流异常退款闭环（P1 / MVP）

### 测试

- [ ] T019 [P] [US1] 编写 ownership-scoped order/logistics read 与 stall calculation Java Test：`OrderLogisticsIntegrationTest.java`。
- [ ] T020 [P] [US1] 编写 deterministic eligibility 与拒绝模型覆盖 amount/eligibility 的 Java Test：`EligibilityServiceTest.java`。
- [ ] T021 [P] [US1] 编写 refund authorization、amount bound、非法状态、idempotency reuse/conflict、timeout recovery Integration Test：`RefundIntegrationTest.java`。
- [ ] T022 [P] [US1] 编写 Python stalled-logistics happy path 与 unknown-write recovery test：`agent-service/tests/integration/test_us1_logistics_refund.py`。

### 实现

- [ ] T023 [P] [US1] 实现 customer-scoped order list/detail API：`OrderController.java`、`OrderService.java`。
- [ ] T024 [P] [US1] 实现物流 API 与权威 stall calculation：`LogisticsController.java`、`LogisticsService.java`。
- [ ] T025 [US1] 实现 deterministic `EligibilityDecision`：`EligibilityService.java`，返回 `eligible`、`allowed_action`、`max_refund_amount`、`approval_required`、rule code/version、reason codes。
- [ ] T026 [US1] 新建 `commerce.refund_requests` migration 与 Entity/Repository：`V002__refund_schema.sql`、`refund/`。
- [ ] T027 [US1] 实现 Transactional Refund Create/Status：`RefundService.java`；每次敏感写入前重新校验 ownership、current state、eligibility、amount 和权威 `approvalRequestId`。
- [ ] T028 [US1] 暴露 Refund 与 After-sales Status API，遵循 `Idempotency-Key`：`RefundController.java`。
- [ ] T029 [P] [US1] 实现 typed tools：`list_user_orders`、`get_order`、`get_logistics`、`check_after_sales_eligibility`、`create_refund_request`、`get_after_sales_status`；统一使用 `success/data/errorCode/retryable/latencyMs/traceId`。
- [ ] T030 [US1] 实现 `understand_request`、单候选 order resolution、`decide_next_evidence`、read-tool execution、evidence validation、`check_eligibility`；`decide_next_evidence` 遵循 `research.md` 的“模型选择受限 capability + 确定性约束”设计。
- [ ] T031 [US1] 实现 Write Execution + Verify-after-write Recovery：`execute_write.py`、`verify_business_state.py`；unknown timeout 必须先 `get_after_sales_status`，必要时同 key 重试。
- [ ] T032 [US1] 在 `graph.py` / `routing.py` 连接显式 LangGraph：START → understand → resolve → evidence loop → eligibility → refund write → verify → finalize；包含最大 step/retry budget。
- [ ] T033 [US1] 实现 Agent Run Create/Execute/Response Serialization：`api/runs.py`；只返回已验证业务 ID/事实，不接受模型自称成功。
- [ ] T034 [US1] 实现最小 Customer Console：`web/src/features/chat/`，展示输入、run status、resolved order、final result 和可折叠 tool timeline。
- [ ] T035 [US1] 添加 US1 Eval Case：正常退款、重复请求、unknown timeout recovery；`eval/datasets/v1/dev/us1_logistics_refund.yaml` + `eval/scorers/business_state.py`。

**Week-2 Gate**：必须真实跑通 Web/API → Agent → Java Tool → PostgreSQL → exactly one RefundRequest → verified result + trace。未通过前禁止 MCP、Dashboard polish、Multi-Agent。

---

## Phase 4：US2 已签收商品改走退货（P1）

- [ ] T036 [P] [US2] 编写 Return eligibility/state/idempotency Java Integration Test：`ReturnIntegrationTest.java`。
- [ ] T037 [P] [US2] 编写 Python Branching Test，证明 `DELIVERED` 证据会把 refund path 改成 return path：`test_us2_delivered_return.py`。
- [ ] T038 [US2] 新建 `commerce.return_requests` schema、Entity/Repository：`V003__return_schema.sql`、`returns/`。
- [ ] T039 [US2] 扩展 eligibility rules 支持 return window、`RETURN`、`RETURN_REFUND`。
- [ ] T040 [US2] 实现受保护 Return Create/Status API；如要求审批，与 Refund 一样验证权威 `approvalRequestId`。
- [ ] T041 [US2] 增加 `create_return_request` Tool，并在 graph/routing 中根据 delivered evidence 进入 Return Path。
- [ ] T042 [US2] 增加 Delivered/Return Eval Case 与 forbidden-direct-refund assertion。

**Checkpoint**：同类用户意图在 US1/US2 下走出不同业务路径。

---

## Phase 5：US3 模糊订单澄清（P1）

- [ ] T043 [P] [US3] 编写多订单 ambiguity、澄清前 zero write、invalid input、cross-user run input denial、valid resume 的 Python Test：`test_us3_clarification.py`。
- [ ] T044 [US3] 实现 Candidate Order Scoring；允许返回 `AMBIGUOUS_ORDER`，禁止猜测，并把 candidate ids 写入 `AgentState`。
- [ ] T045 [US3] 实现 LangGraph interrupt/checkpoint → `WAITING_USER` 以及 resume validation：`ask_clarification.py`、`graph.py`。
- [ ] T046 [US3] 实现 `POST /api/v1/agent/runs/{runId}/input`，包含 authenticated ownership + run-state validation。
- [ ] T047 [US3] 在 `ClarificationPanel.tsx` 实现订单选择与 resume UI。
- [ ] T048 [US3] 增加 ambiguity Eval Case，并要求澄清前 `max_write_count: 0`。

---

## Phase 6：US4 高风险人工审批（P2）

- [ ] T049 [P] [US4] 编写 Approval 状态迁移/Auth/Binding Java Test：`PENDING → APPROVED|DENIED|EXPIRED`、终态不可逆、run/order/action/amount binding、non-approver denial。
- [ ] T050 [P] [US4] 编写 Python HITL Test，证明 Agent 不能 self-approve、伪造 approval state 或使用其他 run 的 approval id。
- [ ] T051 [US4] 新建 `commerce.approval_requests` schema 与 Entity/Repository：`V004__approval_schema.sql`、`approval/`。
- [ ] T052 [US4] 实现 Approval Create/List/Decision API；List/Decision 要求 `APPROVER` role 并写 Audit。
- [ ] T053 [US4] 实现 `request_human_approval` Tool，返回权威 `approvalRequestId`，并进入 `WAITING_APPROVAL`；Agent 不得生成 approval token/status。
- [ ] T054 [US4] 实现 owner-authorized Agent Resume；恢复前重新读取 Java Approval 状态并验证 run/order/action/amount binding。
- [ ] T055 [US4] 实现最小 Approval Center：展示 order/action/amount/risk reason/evidence 与 Approve/Deny。
- [ ] T056 [US4] 增加 high-risk、denied、cross-bound approval id、attempted self-approval Eval Case。

---

## Phase 7：US5 无法自动处理时安全转人工（P2）

- [ ] T057 [P] [US5] 编写 retry budget、no-progress loop、dependency timeout、`MANUAL_REVIEW`、safe stop、escalation Python Test。
- [ ] T058 [P] [US5] 编写 SupportTicket create/ownership/audit Java Test。
- [ ] T059 [US5] 新建 `commerce.support_tickets` schema 与 Entity/Repository；只保存结构化 evidence summary/reason code。
- [ ] T060 [US5] 实现受保护 SupportTicket Create API。
- [ ] T061 [US5] 实现 error contract normalization、no-new-evidence detection、max-step enforcement、`escalate_or_safe_stop` Node。
- [ ] T062 [US5] 实现 `create_support_ticket` Tool，并附带现有 structured evidence/run id。
- [ ] T063 [US5] 增加 dependency failure、conflicting state、max-step、manual-review Eval Case。

---

## Phase 8：US6 政策检索与解释（P2 / 可延期）

该阶段不得阻塞 Portfolio MVP。如果 US1–US4、Safety、Eval 尚未稳定，可以整体延期。

- [ ] T064 [P] [US6] 编写 effective-date、citation metadata、expired/conflict policy、retrieval prompt-injection Test。
- [ ] T065 [US6] 如确认需要向量检索，创建 pgvector 与 `policy.policy_documents` / `policy.policy_chunks`；否则允许先使用版本化 Policy Lookup。
- [ ] T066 [P] [US6] 创建 synthetic AfterSalesPolicy 文档：general refund、logistics exception、electronics return、manual-review。
- [ ] T067 [US6] 实现 Policy Ingestion/Chunking/Embedding（仅启用 Vector Retrieval 时）。
- [ ] T068 [US6] 实现 metadata-filtered Policy Retrieval，返回 document code/version/effective date/section/score/conflict flags。
- [ ] T069 [US6] 实现 `policy_search` Tool 与 Citation Rendering，明确阻止 Policy Text 修改 tool allowlist、auth、eligibility、amount、approval。
- [ ] T070 [US6] 增加 policy citation、expired/conflict、retrieval injection Eval Case。

---

## Phase 9：Polish / Eval / Reproducibility

- [ ] T071 实现 CLI/file-first Eval Runner：调用 Reset Contract、执行 Agent、采集 final business state / tool trace / latency / token，输出 JSON 到 `eval/reports/`。
- [ ] T072 [P] 实现 Scorer：task success、tool selection、parameter correctness、business-state correctness、policy compliance、unsafe action、duplicate write、平均 Tool 数、latency/token；retrieval case 增加 citation/retrieval scorer。
- [ ] T073 实现诚实的 Fixed-workflow Baseline：`eval/baselines/fixed_workflow.py`；复用同一 Tool Contract 与权限，不故意做残。
- [ ] T074 冻结 Dataset：不少于 60 cases，目标约 74；`dev/`、`test/`、`manifest.yaml` 分离；安全 case 按 threat category 覆盖而不是只凑数量。
- [ ] T075 在相同 frozen config 上运行 Baseline/V1，生成 Error Taxonomy 与 Raw Report；模型相关 routing case 记录 model config，必要时重复运行并报告稳定性。
- [ ] T076 仅针对最大 dev-set error category 做一次可归因优化，并保存 Before/After Evidence：`eval/reports/optimization-1.md`。
- [ ] T077 [OPTIONAL] Run Trace / Eval Dashboard 不阻塞核心交付；优先在 Customer Console 内嵌 Trace，并直接通过静态 JSON/Markdown 展示 Eval Report。
- [ ] T078 增加跨服务 Contract Validation：两个 OpenAPI、`eval-internal-api.md`、Tool Mapping。
- [ ] T079 增加 adversarial E2E：cross-user commerce/run、prompt injection、approval bypass/cross-binding、duplicate write、unknown write result、arbitrary tool/URL。
- [ ] T080 增加 CI：Java Test、Python Test、Frontend Build、Contract Check。
- [ ] T081 完成 Docker Compose clean startup、seed、health check 与三个核心 Dockerfile。
- [ ] T082 执行 `quickstart.md` 全部核心场景，记录 pass/fail 并修 blocker。
- [ ] T083 将根 `README.md` 从当前最小项目入口升级为最终作品集交付版本：补充最终架构、真实本地启动方式、60–90 秒 Demo、仅实测 Eval 数字、Known Limitations，以及“不是真实支付/生产 ERP”的明确说明；不得删除历史阶段说明以掩盖实现范围变化。

---

## 依赖顺序

```text
Phase 1 Setup
   ↓
Phase 2 Foundational
   ↓
US1 Logistics Refund  ← 首个强制纵向切片
   ↓
US2 Delivered Return
US3 Clarification
US4 Approval
   ↓
Portfolio MVP Gate
   ↓
US5 / US6 / Baseline / Optimization / UI Polish 按真实开发速度决定
```

单人开发按优先级顺序执行，不为了并行而人为拆工作。

## Portfolio MVP 定义

简历可用版本优先完成：

- Setup + Foundation；
- US1 + US2 + US3 + US4；
- Auth / DB Boundary；
- Idempotency / Unknown-write Recovery；
- Agent Value Gate；
- Structured Trace；
- 冻结 Eval；
- Customer Console + Approval Center；
- Docker Compose；
- 60–90 秒 Demo；
- README 中仅使用真实测量结果。

US5、US6、独立 Trace 页面、Eval Dashboard、MCP、额外基础设施不得阻塞该版本。

## Scope Guard

除非有新的可测需求，否则不加入：Multi-Agent、Kafka、Kubernetes、Redis-as-core、独立 Vector DB、真实支付网关、真实淘宝/JD 集成、商家营销、售前推荐、通用全渠道客服、Model Fine-tuning、装饰性 Admin CRUD。

## Notes

- `.specify/memory/constitution.md` 为最高约束。
- 所有 state-changing task 都必须保持 Agent 与 Java Business Authority 边界。
- 不把 raw SQL、任意 URL/Internal Endpoint 或 DB Credential 暴露给 Agent。
- 不存储/展示 hidden chain-of-thought。
- 未有可复现 Eval 前，README/简历不得把 target 写成 achievement。
- 按 task 或小逻辑组提交，保证可回退和 bisect。
