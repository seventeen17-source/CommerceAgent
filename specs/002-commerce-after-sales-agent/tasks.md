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

- [X] T001 创建并维护当前阶段真实需要的根项目结构与 `README.md`；`commerce-backend/`、`agent-service/`、`web/`、`infra/` 随对应 Setup Task 产生；`eval/`、`knowledge/policies/` 在首次产生真实内容的对应任务中创建，**不得仅为满足目录结构提交空目录**；根 `README.md` 只记录当前真实状态、设计入口、计划技术栈和第一实现目标，不提前填写未实测成果。
- [X] T002 使用 Spring Initializr 生成 `commerce-backend/`：Java 21、Maven、Spring Boot 4.1.1、group `com.seventeen17`、artifact/name `commerce-backend`、package `com.seventeen17.commerceagent`；依赖 Spring Web、Spring Security、Validation、Spring Data JPA、PostgreSQL Driver、Flyway Migration、Actuator、Testcontainers；保留 `mvnw`、`mvnw.cmd`、`.mvn/`。
- [X] T003 [P] 使用 `uv init --python 3.13` 初始化 `agent-service/`，加入 FastAPI、Uvicorn、LangGraph、Pydantic Settings、httpx、PostgreSQL/async DB、pytest、pytest-asyncio；依赖解析后提交 `uv.lock`。
- [X] T004 [P] 使用 Vite React + TypeScript 初始化 `web/`：`npm create vite@latest web -- --template react-ts`，保留 Vite/TS 基线配置。
- [X] T005 配置 PostgreSQL 与逻辑 schema（`commerce`、`agent`、`policy`、可选 `eval`）到 `infra/docker-compose.yml` 和 `.env.example`；设计独立 DB role，使 Agent Service 对 `commerce.*` 无直接权限；允许使用 pgvector-capable 镜像，但 **T005 不启用 `vector` extension、不创建向量表**，是否启用留给 US6/T065。
- [X] T006 [P] 在 `commerce-backend/pom.xml` 配置 Java format/static analysis/test 插件，在 `agent-service/pyproject.toml` 配置 Python lint/type-check。
- [X] T007 [P] 配置 dev/test/eval：`commerce-backend/src/main/resources/application.yml`、`commerce-backend/src/test/resources/application-test.yml`、`agent-service/app/config/settings.py`。

**Checkpoint**：三端空壳可启动并连接本地 PostgreSQL；Java 21 / Python 3.13 / Docker 版本已验证；根 README 能准确反映当前阶段且不包含未实测成果。

---

## Phase 2：Foundational

**目标**：实现所有故事共用的安全、存储、Trace、Error 与 Agent State 基础。

- [X] T008 创建初始 Flyway migration：`commerce.users`、`commerce.orders`、`commerce.order_items`、`commerce.shipments`、`commerce.logistics_events`、`commerce.after_sales_rules`、项目自有 `agent.agent_runs`、`agent.tool_executions`、`commerce.audit_logs`；文件 `commerce-backend/src/main/resources/db/migration/V001__core_schema.sql`。第三方 LangGraph checkpoint 表若由库自管理，放到独立 schema 并按 `research.md` 记录 migration 例外。
- [X] T009 [P] 实现 User、Order、OrderItem、Shipment、LogisticsEvent JPA Entity/Repository：`commerce-backend/src/main/java/com/seventeen17/commerceagent/order/`、`logistics/`；保留 immutable ownership、optimistic `version`、权威价格/状态。
- [X] T010 [P] 实现 `AfterSalesRule` 持久化：`eligibility/`；包含唯一 `rule_code`、version/effective dates、物流/退货/金额/审批阈值、`allowed_action`、`active`。
- [X] T011 实现本地 JWT 认证和 role-aware principal：`security/`；Customer API 只能从 principal 推导 ownership。
- [X] T012 [P] 实现与 `contracts/error-contracts.md` 对齐的统一 Error Envelope：`common/error/`。
- [X] T013 [P] 实现结构化业务/安全 Audit Writer：`audit/`；禁止保存 hidden chain-of-thought 和 raw token。
- [X] T014 创建 dev/eval fixture loader，预置 `customer-001`、`customer-002`、`approver-001`、订单/物流/规则，以及 `contracts/eval-internal-api.md` 的 reset endpoint；只能在 test/eval profile 注册。
- [X] T015 [P] 定义显式 `AgentState`：`agent-service/app/agent/state.py`；包含 run id、principal context、intent、candidate/resolved order、evidence、eligibility、approval、tool history、step/retry budget、write/verification、terminal status。
- [X] T016 [P] 实现类型化 Java API Client：`agent-service/app/clients/commerce_client.py`；负责 auth-context 传递、timeout、统一 response validation；通过 Java `GET /api/v1/me` 获取由 verified JWT subject + `commerce.users` 解析出的权威 `userId/role`，Python 不得猜 role 或直查 `commerce.users`；对 Java-owned response value（如 `allowedAction` / approval `status`）保持 forward-compatible open string，未知值必须受控 `SAFE_STOP`，不得因消费端镜像 enum 直接炸成 500；每次 Java Tool HTTP 调用传播由应用代码生成的 `X-Trace-Id`，不得接受 model output 自定义 trace id；同步把 Java `TraceIdFilter` 收紧为“仅接受格式/长度校验通过的入站 correlation id，否则生成新的 server trace id”；token/principal 不能进入 model prompt。
- [X] T017 实现持久化 Agent Run/Checkpoint/Structured Tool Trace：`agent-service/app/trace/`；支持 `RUNNING`、`WAITING_USER`、`WAITING_APPROVAL`、`COMPLETED`、`ESCALATED`、`FAILED`、`SAFE_STOP`；Tool Trace 必须持久化 `run_id + step_index + trace_id`（以及 error/retry/write-verification 摘要），确保 failed run 可定位到具体跨服务 Java 请求；持久化前必须继续执行 AgentState 的递归敏感信息护栏，raw token/hidden reasoning 不得进入 checkpoint/trace；run update/resume 必须使用数据库行锁或 compare-and-set/version 条件，保证同一旧 checkpoint 的并发 resume 最多一个成功，禁止两个请求从同一 WAITING 状态分叉执行；定义 terminal run 的 retention/cleanup policy，运行中/等待中的 checkpoint 可恢复，终态详细 checkpoint/tool trace 不得无限期无界增长。
- [X] T018 实现 FastAPI JWT 验证、principal context、run ownership 与 run/status/event skeleton endpoint：`agent-service/app/security/`、`api/runs.py`、`main.py`；补齐 `agent-service/app/config/settings.py` 的 JWT verification 配置，复用 `.env.example` 已有的 `COMMERCE_JWT_ISSUER` / `COMMERCE_JWT_SECRET`，当前 local fixture 明确使用 HS256；本地验证 JWT 后仍以 Java `GET /api/v1/me` 返回的当前 `userId/role` 作为 PrincipalContext 的权威角色来源（Java 会再次验证 token 并读取当前用户状态/角色），不得从请求文本或模型输出构造 role；raw JWT/secret 不得进入 AgentState、prompt 或 trace；用户不得读取/恢复其他人的 run；浏览器链路验证把 Run 创建、Run 查询和 events 查询作为步骤 08–10 接入既有 CommerceAgent Flow Playground 左侧调用链，真实请求控件和响应显示在所选步骤右侧 `STEP DETAIL`，不得另开底部 T018 区块或替换 T016 已有测试按钮。

**Checkpoint**：已认证 synthetic state 与可恢复、owner-scoped AgentRun 能创建和追踪，但还不能执行退款/退货。

---

## Phase 3：US1 物流异常退款闭环（P1 / MVP）

### 测试

- [X] T019 [P] [US1] 编写 ownership-scoped order/logistics read 与 stall calculation Java Test：`OrderLogisticsIntegrationTest.java`。
- [X] T020 [P] [US1] 编写 deterministic eligibility 与拒绝模型覆盖 amount/eligibility 的 Java Test：`EligibilityServiceTest.java`。
- [X] T021 [P] [US1] 编写 refund authorization、amount bound、非法状态、idempotency reuse/conflict、timeout recovery Integration Test：`RefundIntegrationTest.java`。
- [X] T022 [P] [US1] 编写 Python stalled-logistics happy path 与 unknown-write recovery test：`agent-service/tests/integration/test_us1_logistics_refund.py`。

### 实现

- [X] T023 [P] [US1] 实现 customer-scoped order list/detail API：`OrderController.java`、`OrderService.java`。→ **已完成**：`GET /api/v1/orders` / `GET /api/v1/orders/{orderId}` 已通过真实 HTTP 集成测试，身份只来自 `CommercePrincipal`，非 CUSTOMER 为 403，cross-owner 与不存在统一为 404 `ORDER_NOT_FOUND`；Java HTTP 定点测试 7/7 通过。
- [X] T024 [P] [US1] 实现物流 API 与权威 stall calculation：`LogisticsController.java`、`LogisticsService.java`。→ **已完成**：新增 `GET /api/v1/orders/{orderId}/logistics` HTTP 边界，复用 T019 `LogisticsService` / `LogisticsStallCalculator`；`LogisticsHttpIntegrationTest` 8/8 通过，Java `clean verify` 全绿；5173 `T024 · LIVE JAVA` 页面实测 owner `order-001` → 200、cross-owner `order-002` → 404 `ORDER_NOT_FOUND`、不存在订单 → 同样 404，验证 Vite → Java → Service → PostgreSQL 的真实读链。
- [X] T025 [US1] 实现 deterministic `EligibilityDecision`：`EligibilityService.java`，返回 `eligible`、`allowed_action`、`max_refund_amount`、`approval_required`、rule code/version、reason codes。→ **已完成并验收**：复用 T020 已验证的 deterministic core，补齐受保护 `POST /api/v1/after-sales/eligibility`、`EligibilityHttpIntegrationTest` 与 Flow Playground live 入口；2026-09-25 本地实测定点测试 **7/7**、Java `clean verify` **BUILD SUCCESS**、Web build 成功、Web lint **0 warnings / 0 errors**；5173 owner `order-001` → 200，cross-owner `order-002` 与 missing → 同样 404 `ORDER_NOT_FOUND`。
- [X] T026 [US1] 新建 `commerce.refund_requests` migration 与 Entity/Repository：**`V003__refund_schema.sql`**（原计划写 V002，但 `V002` 已被 T017 的 `V002__agent_run_checkpoint.sql` 占用；编号冲突在 T021 报出并修正）、`refund/`；同步扩展 T014 `FixtureLoader.clearFixtureState()`，清理 refund 与本阶段引入的 idempotency state，保证 Eval reset 不残留写入结果。→ **已随 T021 一并交付**：schema（含两个唯一约束）、`RefundRequest`/`RefundRequestRepository`、fixture reset 清理退款行（否则外键会让 reset 直接失败）。
- [ ] T027 [US1] 实现 Transactional Refund Create/Status：`RefundService.java`；每次敏感写入前重新校验 ownership、current state、eligibility、amount 和权威 `approvalRequestId`。→ **部分已随 T021 交付**：`createRefund` 已实现 ownership / current state / eligibility / amount 的写前重校验、幂等重放与冲突、订单行锁、退款行 + 订单投影 + 审计的同事务写入，以及 `listRefunds` 状态读面。**仍未完成**：权威 `approvalRequestId` 绑定校验（V1 没有审批记录表，任何审批引用一律 fail closed 为 `INVALID_PARAMETER`，US4/T049 实现真正的绑定）。
- [X] T028 [US1] 暴露 Refund 与 After-sales Status API，遵循 `Idempotency-Key`：`RefundController.java`；`GET /orders/{orderId}/after-sales` 实现可选 `idempotencyKey` 过滤，供 T022/T031 unknown-write recovery 只确认当前逻辑写，不能把同订单上的其他退款误认成自己的成功。→ **已完成并验收**：新增 `POST /api/v1/refunds` 与 `GET /api/v1/orders/{orderId}/after-sales`，身份只来自 `CommercePrincipal`；退款写入复用 T021 的 ownership/current-state/eligibility/amount 重校验与幂等保护；after-sales 读面按 authenticated user + order + idempotencyKey 精确过滤，错误 key 返回显式空 `refunds`；`RefundHttpIntegrationTest` **8/8**，Maven **BUILD SUCCESS**。Flow Playground 已接入 `T028 · LIVE REFUND` 的 create + verify 控件；最近一次手工 live 尝试命中了未重启的旧 8080 Java 进程，因此 README 不把该次 5173 尝试声明为成功验收证据。
- [X] T029 [P] [US1] 实现 typed tools：`list_user_orders`、`get_order`、`get_logistics`、`check_after_sales_eligibility`、`create_refund_request`、`get_after_sales_status`；统一使用 `success/data/errorCode/retryable/latencyMs/traceId`。→ **已完成并验收**：新增 `app/tools/`（统一 `ToolEnvelope`、`ToolRisk`、`ToolRegistry`、`CommerceTools`）；六个 US1 capability 通过显式 allowlist 注册并绑定到实现，`create_refund_request` 唯一标记为 `HIGH_WRITE`；身份凭据绑定在 `CommerceTools` 上，不暴露给模型；只读/判定 Tool 统一把 Java/transport/参数失败归一为 Tool Envelope；退款写超时明确返回 `WRITE_TIMEOUT_UNKNOWN + retryable=false`，禁止 Tool 层盲重试，必须由 T031 先 `get_after_sales_status` 再决定同 key 恢复。2026-09-28 最终验收：Python `ruff check` / `ruff format --check` / `mypy app` 全绿，`pytest -q` **285 passed, 6 skipped, 6 warnings**；Web `npm.cmd run build` / `npm.cmd run lint` 全绿。为满足可观察验收，补充 dev/test-only Tool debug route 与 `T029 · LIVE TOOL` Flow Playground，5173 已实测 order / logistics / eligibility / after-sales 四条真实 Tool 链，并验证不存在 key 的显式空结果、cross-owner 与 missing order 的 `ORDER_NOT_FOUND` concealment；high-write `create_refund_request` 刻意不暴露在 debug route。
- [X] T030 [US1] 实现 `understand_request`、单候选 order resolution、`decide_next_evidence`、read-tool execution、evidence validation、`check_eligibility`；`decide_next_evidence` 遵循 `research.md` 的“模型选择受限 capability + 确定性约束”设计。→ **已完成并验收**：真实 OpenAI-compatible LLM 只做请求理解与受限 evidence capability 建议；订单线索必须经 Java ownership-confirmed `get_order` 才能成为 `resolved_order_id`；`decide_next_evidence` 仅允许 `get_logistics` / `READY_FOR_ELIGIBILITY`，并由确定性 guard 复核 registry risk、当前状态与重复证据；成功 Tool 结果才可进入 `EvidenceItem`，`stalledHours` 等事实继续由 Java 计算；最终 eligibility 只由 Java `EligibilityService` 决定。2026-09-28 最终验收：Python `ruff check` / `ruff format --check` / `mypy app` / `pytest -q` 全绿，`pytest` **333 passed, 6 skipped, 6 warnings**；Web `npm.cmd run build` / `npm.cmd run lint` 全绿；5173 `T030 · LIVE AGENT` 实测 owner `order-001` → `completed=true`，cross-owner `order-002` → `completed=false + ORDER_NOT_FOUND`，且不进入物流/eligibility 后续链。正式 LangGraph 装配仍由 T032 完成。
- [X] T031 [US1] 实现 Write Execution + Verify-after-write Recovery：`execute_write.py`、`verify_business_state.py`；unknown timeout 必须先 `get_after_sales_status`，必要时同 key 重试。→ **已完成并验收（2026-09-29）**：`app/agent/execute_write.py`（T022 的 write-ahead intent、单次尝试、未知结果先读权威状态、同 key 有限预算重试、预算耗尽 → `UNKNOWN`、intent 落盘失败则不发请求；并已改写为经 T029 typed tools 执行与恢复）、`app/agent/verify_business_state.py`（按同一 idempotency key 读 Java 权威 after-sales 状态产出 `VerificationOutcome`，自己不重试）、`PostgresRunStore.checkpoint_state()`（CAS 全量状态快照，拒绝借它改 status）、`app/api/dev_t031.py`（dev-only live harness）均已交付并有测试。**收口时发现这 9 个远端提交从未跑过 Python 门禁**：修掉 5 处 `ruff check` 违规（import 未排序、2 处超长行、未使用导入、无用 `noqa`）与 4 个待格式化文件后，四条门禁全绿 —— `ruff check .` **All checks passed**、`ruff format --check .` **73 files**、`mypy app` **Success 42 source files**、`pytest -q` **344 passed, 6 skipped**。**生产接线仍由 T032 承接**：当前 `verify_business_state` 的唯一非测试调用方是 dev-only 路由，端到端 Gate 尚未跑通。
- [X] T032 [US1] 在 `graph.py` / `routing.py` 连接显式 LangGraph：START → understand → resolve → evidence loop → eligibility → refund write → verify → finalize；包含最大 step/retry budget。→ **已完成并验收（2026-09-29）**。**用户手工完成 live 验收（两条入口 × 两个终态）**：**（a）页面 `POST /runs`**：`dead3781-82db-4aea-8868-b3de895f6e29` → `status=COMPLETED` / `currentNode=finalize` / `stepCount=8` / `version=11`，并经数据库交叉核对（run 行为 `COMPLETED, step_count=8, version=11`）；该轮写被 Java 以 `DUPLICATE_AFTER_SALES + retryable=false` 拒绝 → 未盲重试 → 读权威 → `VERIFIED_FAILURE`（如实报"未产生资金动作"）。**（b）`/input` 入口 + `WAITING_USER` 终态**：`e12618e1-033e-497a-b811-f6509b9a9103` 先 `status=WAITING_USER`（4 个候选不猜，`stepCount=1/version=3`），澄清后经 `/input` 认领并重跑 → `status=COMPLETED` / `currentNode=finalize` / `stepCount=7` / `version=12` / `resolvedOrderId=demo-order-stalled-001`（**澄清真的解决了歧义**）；该轮 Java 判 `eligible=false + MANUAL_REVIEW` → 图**一个字节都没写**（`write=NOT_ATTEMPTED`，连 `write_intent` 都不存在）→ `COMPLETED` + "没有产生退款写入" ✓（`verificationStatus=NOT_RUN`，与"没写"一致）。**过程教训（保留）**：AI 第一版话术用裸 `"我要退款"` 缺情境 → 理解层判 `intent=UNKNOWN` → 又回 `WAITING_USER` 形成循环；**不是代码 bug，是测试场景设计错**（`route_after_understand` 的设计就是"认不出意图就问用户"）。**验收方式说明**：AI 在验收前用 HTTP 直接打 API 跑通的同一链路只记为 **smoke 预检**、不作验收证据（对应 AGENTS.md §9.6「用户本地是最终构建事实来源」与仓库既有口径「手工 5173 尝试才构成 live 验收证据」）。**过程证据**：首次点击被页面拦下——「哪些步骤不需要 runId」是一张**否定清单**，新增步骤漏登记 → 只有真正点击页面才暴露（类型检查与单测都看不见），修复为 `c9aa902`，并用「`t031-live-write` 与 `t032-live-run` 在文件中各处出现次数相等（12=12）」核对无第二次遗漏。交付物：`app/agent/graph.py`（`GraphState` + 显式条件边目标表 + 装配校验 + `compile(checkpointer=None)`）、`routing.py`（`Node` / `SafeStopReason` / `HandoffReason` / `Decision` / `TerminalDecision` + 预算守卫 + 8 个纯路由）、`nodes.py`（**10 / 10 节点**）、`runtime.py`（`RunSession` 三个写 seam + `drive_graph`：版本跟踪、边界写延迟一步、失败收尸）、`wiring.py`（10 节点 + 9 依赖唯一组装点）、`runs.py`（`POST /runs` 创建即驱动 + 可注入 `RunDriver` 接缝）、`tool_tracing.py`（五条碰 Java 的路径全部上报 trace）、Flow Playground 的 `T032 · LIVE GRAPH RUN` 步骤。门禁：`ruff check` All checks passed / `ruff format --check` **86 files** / `mypy app` **48 files** / `pytest` **475 passed, 6 skipped**；真库集成 **68 passed**。**（以下为收口过程中的记录，保留作过程证据；其"未完成"列表已被上面的验收结论取代）**：已交付 `app/agent/graph.py`（`GraphState` + 显式条件边目标表 + 装配校验 + `compile(checkpointer=None)`）、`app/agent/routing.py`（`Node` / `SafeStopReason` / `HandoffReason` / `Decision` / `TerminalDecision` + 预算守卫 + 8 个纯路由）、`app/agent/nodes.py`（**10 / 10 节点**，含终态 `finalize` / `safe_stop` / `waiting_user`）、`app/agent/runtime.py`（`RunSession` 的三个写 seam + `drive_graph`：版本跟踪、边界写延迟一步、失败收尸）、`app/agent/wiring.py`（10 节点 + 9 依赖的唯一组装点）；`state.py` 增 `advance()` 作为唯一校验变更入口（实测 langgraph 1.2.11 的节点更新不重新校验模型，`model_copy(update=…)` 会静默关掉 `extra="forbid"`、预算与凭据扫描）；`runs.py` 的 `/input` 与 `/resume` 现在真的组装图并驱动 run。**未完成**：5173 live 验收、`agent.tool_executions` 工具 trace 接线、`/input` 与 `/resume` 的 HTTP happy-path 用例（`POST /runs` 已有）。**三个入口现在都会组装图并驱动 run**（`POST /runs` 是第一次 invocation 的唯一入口——契约没有 execute 端点；驱动是可注入的 `RunDriver` 接缝，`check` 在写任何东西之前拒绝，避免留下没人能推进的 `RUNNING` run）。**真库 E2E 已在真实 PostgreSQL 上跑通**：`tests/integration/` 共 **65 passed**（含 `test_runtime_seam.py` 6 个新用例）。门禁：`ruff check` / `ruff format --check` **83 files** / `mypy app` **47 files** / `pytest` **451 passed, 6 skipped**（6 个 skip 全部是 `test_state_secret_guard.py` 的字段类型参数化，与数据库无关）。**环境注意**：PostgreSQL 在 `infra/docker-compose.yml` 的 `postgres` 容器里，Docker 未启动时集成用例按设计 skip（约 49 个）而非 fail。
- [X] T033 [US1] 实现 Agent Run Create/Execute/Response Serialization：`api/runs.py`；只返回已验证业务 ID/事实，不接受模型自称成功。→ **已完成并验收（2026-09-29）**：`AgentRunView` 补齐契约已发布但服务从未返回的 `finalMessage` / `approvalRequestId`，并新增三项 T033 真正要求的字段——`verificationStatus`（**权威确认了什么**，不是写响应说了什么）、`verifiedRefundRequestId`（**只在 `VERIFIED_SUCCESS` 时非空**，其余四种状态与 payload 已回收一律 null）、`finalMessage`（由**终态 + 校验结果确定性推导**，每个终态一条分支；`PENDING` 与 `UNKNOWN` 同归"结果未确立"，因为写可能还在飞，把它说成"没有写入"就是编造结论）。`version`（客户端做 CAS 重试要传回的值）与 `checkpointCompactedAt`（区分"没有校验过"与"payload 已被保留策略回收"这两种不同事实）一并补进 `contracts/agent-api.openapi.yaml`。**Create/Execute 的接线属 T032**（`POST /runs` 创建即驱动），本任务只负责序列化。测试：`tests/unit/test_run_view.py` 11 条 + `test_run_api.py` 的响应形状用例。门禁：`ruff check` All checks passed / `ruff format --check` **86 files** / `mypy app` **48 files** / `pytest` **475 passed, 6 skipped**；真库集成 **68 passed**。
- [X] T034 [US1] 实现最小 Customer Console（**可信客户界面**，客户视角）：`web/src/features/chat/`；聊天为主 + 订单卡片为辅，只呈现客户能理解的四件事（我发了什么 / 正在处理 / 最终结果 / 需要我补充什么），**内部事实**（`currentNode` / `stepCount` / `version` / `verificationStatus` / `write.status`）**不进客户界面**，保留在 Flow Playground。范围上限两个页面，不引入设计系统 / 响应式矩阵 / 登录页；`WAITING_USER` 必须用客户安全的方式说明需要补充什么（候选订单），而非只给一句"等待补充信息"。范围定义见 `spec.md` 的「用户故事 1」客户界面范围段。→ **实现完成（2026-09-29），待用户手工验收**（勾选前必须由用户在浏览器完成，AI 预检不计入验收证据）：交付 `web/src/features/chat/CustomerConsole.tsx`（聊天为主 + 订单卡片为辅；`status` 翻译成客户话术而非打印枚举；token 只存内存；**无轮询**——`POST /runs` 创建即驱动，响应本身已带终态或澄清）+ `web/src/App.tsx` 双标签切换（**默认仍是 Flow Playground**，既有验收流程未改）+ 契约增量 `clarification.kind` / `candidateOrderIds`（`agent-api.openapi.yaml` + `AgentRunView` + 4 个单测）。门禁：`ruff` / `ruff format --check` **86 files** / `mypy app` **48 files** / `pytest` **482 passed, 6 skipped** / 真库集成 **71 passed** / web `oxlint` 0 warnings 0 errors、`tsc` exit 0、`vite build` ✓。**AI 预检（不计入验收）**：真实服务上 `28776e5e-e41c-496a-85df-d5d13a70a4f7` → `WAITING_USER` + `clarification={"kind":"ORDER_AMBIGUOUS","candidateOrderIds":[4 个]}`；Console 按钮原样话术 `是这一单：demo-order-stalled-001` → `COMPLETED` + `resolvedOrderId=demo-order-stalled-001`，终态时 `clarification` 自动回到 null。**已知缺口**：`web/` 无自动化测试设施，本界面目前只有 lint/tsc/build 与手工验收覆盖。→ **用户手工验收通过（2026-09-29，浏览器）**：四步交互全部由用户在客户界面完成——①「在吗」→"我还不太确定你的诉求，能再说明一下吗？"（`INTENT_UNKNOWN`，无按钮 ✓）②「我的包裹物流三天没动了，我要退款」→"你名下有好几笔订单，请告诉我是哪一笔" + **4 个候选订单按钮**（`ORDER_AMBIGUOUS`，**同一个 run 续跑** ✓）③点 `demo-order-delivered-001` → 结果卡片"已完成，本次没有产生退款写入。"+ 订单行 ✓ ④界面全程**未出现任何内部事实**（`currentNode` / `stepCount` / `version` / `verificationStatus` / `write.status` 均不可见 ✓）。**旁证（真实浏览器）**：`customer-001` 那次会话（run `830c5fe2`，`COMPLETED`，steps=9）证明 `send()` 修复生效——同一 run 的 `user_request` 里同时存在首句与 `[follow-up]` 文本 ✓，而不是另起一个 run ✓。**行为说明（非缺陷）**：用户点的是 `DELIVERED` 订单，属 US2 退货范围（T036–T042 未实现），故 Java 判定不可直接退款、图未写入任何数据 ✓ —— 权威边界在生效，Agent 没有自作主张给已签收订单退款 ✓。
- [X] T035 [US1] 添加 US1 Eval Case：正常退款、重复请求、unknown timeout recovery；首次创建 `eval/`，并落地 `eval/datasets/v1/dev/us1_logistics_refund.yaml` + `eval/scorers/business_state.py`。→ **实现完成（2026-09-29），待用户验收**（复选框不勾）：① `eval/scorers/business_state.py` 判分器——只读**事后真实业务行**，明确拒收 `status` / `finalMessage` / tool 调用成功，配 5 个用例；② `eval/datasets/dev/us1_logistics_refund.yaml` 三个 case（happy / duplicate / unknown-write-timeout），第三个按"**结果 + 机制**"双断言（`recoveryReadRequired` ✓ —— 只断结果会在"Agent 什么都没做"时假通过 ✗）；③ `eval/runner.py` 最小执行器（reset → `POST /runs` → 读业务状态 → 打分 → 报告）。**关键行为实测**：reset 端点不可用时 **exit 2 记为 infrastructure failure** ✓，对当前 dev profile 后端输出 `[infrastructure] ×3` + `{"infrastructure": 3}` ✓ —— 既不是假通过 ✗，也不是"模型失败" ✗。**布局与计划有意不同**：计划写 `eval/datasets/v1/dev/…`，实际沿用仓库已有约定 `eval/datasets/dev/` + 文件内 `datasetVersion: v1`（同目录已有 `manifest.json` ✓），避免 case 有两个去处。门禁：`ruff check` All checks passed / `ruff format --check` **3 files** / `pytest eval/tests` **5 passed**。**跑出真实数字的前置**：Java 必须以 `eval` profile 启动（`EvalFixtureController` 为 `@Profile({"test","eval"})`）→ `.\mvnw.cmd "-Dspring-boot.run.profiles=eval" spring-boot:run`；dev profile 下 reset 不存在，执行器会（正确地）拒绝判分。**第一次真实运行结果**（Java `dev,eval`，Agent 8000）：`{"pass": 2, "fail": 1}` —— `us1-happy-refund` **pass**（真判断：我一度把状态值编成 `PENDING/SUCCEEDED`，它就把一个正确 run 判成 fail ✓，改成真实的 `CREATED` 后才通过 ✓）、`us1-duplicate-request` **pass**（真判断：runner 原先只发一次请求 ✗ → 断言无内容 ✓，改为 `repeatRequest: 2` 发两次独立 run 后仍只有一行 ✓，幂等在真实链路上被验证 ✓）、`us1-unknown-write-timeout` **fail**（**预期内**：断言已收紧为"先 `WRITE_TIMEOUT_UNKNOWN`、其后才有权威读" ✓，而**注入写超时的机制尚不存在** ✗ —— 属 T031 dev 故障注入 / T071 范围，不在本任务内 ✓）。**工程缺口（发现）**：`eval` profile **只有 `@Profile` 标注、没有配置** ✗（数据源只写在 `application.yml` 的 `dev` 文档里第 55–73 行）→ 单独激活 `eval` 会 `Failed to configure a DataSource` ✓，当前需 `dev,eval` 同时激活；**正式修法应作为 T071 的前置条件** ✓。另：`/internal/eval/**` 位于 `anyRequest().authenticated()` 之后 ✓ → reset 必须带 token ✓，且 **401 不能用来判断端点是否注册** ✗（runner 已修 ✓）。**验收方式**：AI 已实际跑通并将三条结果的成色逐条说明，**用户过目后确认继续** ✓。

**Week-2 Gate**：必须真实跑通 Web/API → Agent → Java Tool → PostgreSQL → exactly one RefundRequest → verified result + trace。未通过前禁止 MCP、Dashboard polish、Multi-Agent。

---

## Phase 4：US2 已签收商品改走退货（P1）

- [X] T036 [P] [US2] 编写 Return eligibility/state/idempotency Java Integration Test：`ReturnIntegrationTest.java`。→ **已交付（2026-09-29）**：落地为 `ReturnEligibilityIntegrationTest.java`（根包 ✓，与 T020 的 eligibility 集成测试同风格 ✓），两个用例：**激活**的 `aDeliveredOrderIsNotEligibleForADirectRefund` 断言"已签收订单不得被判成直接退款"（断言**决策**而非代码路径 → 今天成立 ✓ 且 T039 之后仍成立 ✓，是回归保险而不是将来要重写的测试 ✓；并刻意种下 US2 禁止的配置——一条在 `DELIVERED` 上授予 `REFUND_ONLY` 的规则 ✓）；**`@Disabled`** 的 `aDeliveredOrderIsRoutedToAReturnAction` 把"还没做的部分"写进代码 ✓。**接缝选择**：T036 落在**已存在的规则层** ✓；数据层的幂等约束测试应与 **T038 建表配对** ✓，状态层随 **T040** ✓（直接引用不存在的类会让整个 `verify` 红 ✗，而不是一条用例红 ✓）。门禁：`spotless:apply` → 定点 test → **`clean verify` BUILD SUCCESS** ✓（`Tests run: 165, Failures: 0, Errors: 0, Skipped: 1` ✓ / `Spotless 98 files clean` ✓ / `BugInstance 0` ✓）。附带还清旧账：`spotless:apply` 因新的 LF 策略规范化整个 Java 树（~100 文件，diff 纯格式 ✓）→ T028 遗留格式债务一并修好 ✓，工作区完全干净 ✓。 **2026-10-06 补修（负例用尚无售后的 DELIVERED 订单 + 断言具名原因 + Java 守卫禁止 REFUND_ONLY 放行）**：① **夹具原来在撒谎** ✗ —— `seedOrder` 把每张订单都写成 `afterSalesStatus=REFUND_REQUESTED`，决策在第一步就以 `ORDER_ALREADY_HAS_AFTER_SALES` 返回，于是"已签收不得直接退款"这条断言**一直为真，而它要守的那条路从未被执行过** ✓；现改为**尚无任何售后动作**的 `DELIVERED` 订单 ✓。② 夹具改对的那一刻就暴露真实漏洞 ✓：`evaluate` 返回 **`eligible=true` + `REFUND_ONLY`** —— `REFUND_ONLY` 分支只在规则声明了停滞阈值时才做冲突检查，这条规则没声明 → `needsLogisticsFacts=false` → 直接放行 ✓。③ 新增 **Java 守卫** `EligibilityService.deliveredOrderCannotTakeADirectRefund(order, action)`（`action==REFUND_ONLY && order.status()==DELIVERED`）：判据取**订单生命周期状态**（权威、一定有值），不取运单 ✓；它是**唯一判据**，被外壳（要不要读物流）与决策层（哪个原因码）共用，两处漂移不可表达 ✓；排在停滞检查**之前**，避免给出误导性的 `LOGISTICS_CONFLICTS_WITH_ORDER` ✓；结论是 **`DENY`**（新增具名原因码 `DELIVERED_ORDER_IS_RETURN_ONLY`）而不是 `MANUAL_REVIEW` —— 转人工等于给"给已签收订单直接打款"留一道门 ✓。④ 断言升级为具名原因码 + `allowedAction != REFUND_ONLY` + `grantsMoneyAction()==false` ✓。⑤ **变异检查**（判据临时改成 `return false`）：恰好这两条新用例红（其中一条显示 `eligible` 变 `true`）、其余 30 条全绿 → 守卫既承重又不误伤 ✓。门禁：`spotless:apply` → 定点 `EligibilityServiceTest` **32 passed** → **`clean verify` BUILD SUCCESS**（`Tests run: 174, Failures: 0, Errors: 0, Skipped: 0` / `Spotless 102 files clean / 0 needs changes` / `BugInstance 0` / JaCoCo 69 classes）✓。契约无需变更：`reasonCodes` 是开放字符串数组 ✓。
- [X] T037 [P] [US2] 编写 Python Branching Test，证明 `DELIVERED` 证据会把 refund path 改成 return path：`test_us2_delivered_return.py`。→ **有意后置到 T041 之后**：本用例要证明"`DELIVERED` 证据把 refund path 改成 return path"，而退货路径由 T041 的 `create_return_request` Tool + graph 分支提供。在 T041 之前它只能是红用例或 `@Disabled` 占位 —— 今天的 `tests/unit/test_graph_routing.py::test_refund_permitting_actions_reach_the_write_node` 正钉着 `RETURN_REFUND` 会进写节点，而 Java `RefundService` 只对 `REFUND_ONLY` 放行退款，因此"退货动作不得进退款路径"这条断言在退货路径存在前无法为真。 **已完成（2026-10-06，与 T041 配对）**：`tests/integration/test_us2_delivered_return.py`（假 Java + 真实路由 `route_after_eligibility` + 真实 `execute_return_write` + 真实 `verify_return_business_state`）**5 条用例** ✓：① 已签收证据 → 分支是 `Node.RETURN_WRITE`、退货写成功、校验 `VERIFIED_SUCCESS`，并且**断言假 Java 的调用日志里没有 `POST /api/v1/refunds`** ✓✓（"退货动作不得进退款路径"这句话只有服务端能作证：只断言"写了一条退货"的测试，在 Agent 同时试着打款的情况下仍然会绿 ✗）；② 答丢之后**先读权威再收尾**（`timeout_after_commit` → `recovered=True`、退货端点只被调用**一次**、仍然没有退款调用）✓；③ 分支由**决策**决定而不是由 Agent 决定（`REFUND_ONLY` / `MANUAL_REVIEW` / `DENY` 三种决策下都不到达退货写，`return_keys` 为空）✓。**门禁**：Python 四条全绿（`ruff` All checks passed / `format` **87 files** / `mypy` **48 files** / `pytest` **498 passed, 6 skipped**）✓。
- [X] T038 [US2] 新建 `commerce.return_requests` schema、Entity/Repository：`V004__return_schema.sql`、`returns/`；同步扩展 T014 fixture reset 清理 return state。→ **已完成并验收（2026-09-29）**：① `V004__return_schema.sql` **逐条镜像 V003** ✓（同样的两层约束：`uq_return_requests_user_idempotency_key (user_id, idempotency_key)` 重试守卫 ✓ + `uq_return_requests_order_id_active` **部分**唯一索引 ✓），活动态谓词写成 **`WHERE status NOT IN ('REJECTED','CANCELLED')`**（fail-closed ✓：以后新增状态默认算活动 ✓，而 `IN (活动态)` 会让新状态自动豁免约束 ✗）；**退货行刻意没有 amount 列** ✓（它记录"哪一单/什么状态/哪条规则批的"✓，钱属于退款行 ✓ —— 两份金额迟早不一致 ✗）。② `returns/`：`ReturnStatus`（词表镜像退款侧 ✓）+ `ReturnRequest`（字段/不可变约定/时间戳生成方式与 `RefundRequest` 一致 ✓；`create(...)` 工厂不接受 status 参数 ✓ 新行永远是 CREATED ✓；刻意没有 `@Version` ✓ 因为 V1 行不可变 ✓）+ `ReturnRequestRepository`（三个 owner-scoped 派生查询 ✓，其中 `findByOrderIdAndUserIdAndIdempotencyKey` 用于"这一笔是不是我这次逻辑写产生的"✓，T031 写后恢复靠的正是这个精度 ✓）。③ `FixtureLoader.clearFixtureState()` 在退款行**旁边**加退货清理 ✓，**位于 orders 之前** ✓（外键 ✓，否则 eval reset FK 失败 ✗）。④ `ReturnIdempotencyIntegrationTest` **三条用例**（断言**约束名**✓，因为两种冲突同为 SQLState 23505 ✓）：同 (user,key) → `uq_return_requests_user_idempotency_key` ✓；同订单两把不同 key → `uq_return_requests_order_id_active` ✓（**这正是只上 D 层防不住的那条** ✓✓）；先置 REJECTED 再插活动行 → **允许** ✓（证明索引是**部分**的 ✓，防"删掉 WHERE 子句把守卫变成'每单只能退一次'"✗）。**过程教训**：第一版三条用例**共用一个 order id** ✗ → 第一条留下的活动行决定了第二条的结局 ✗（看起来像约束写错，实际是"一个用例继承了另一个用例的世界"✓）→ 用 `@AfterEach` 清本订单行解决 ✓。**门禁**：`spotless:apply` → 定点 test（3 passed ✓）→ **`clean verify` BUILD SUCCESS** ✓（`Tests run: 168, Failures: 0, Errors: 0, Skipped: 1` ✓ / `Spotless 102 files clean` ✓ / `BugInstance 0` ✓ / Flyway 在真实 PostgreSQL 应用 V004 ✓）。**数据现状**：表在 dev 库由下次启动自动创建 ✓，**当前 0 行** ✓（正确 ✓ —— 退货路径要等 T039 规则 / T040 API / T041 Tool 接通后才可能写入第一行 ✓）。
- [X] T039 [US2] 扩展 eligibility rules 支持 return window、`RETURN`、`RETURN_REFUND`。→ **已完成并验收（2026-09-29）**：① **替换掉那条自我标注的占位**（代码原文写着"T039 会补上 return window 判定并替换这条分支"）：`RETURN / RETURN_REFUND` 不再一律转人工，而是判定窗口 —— **窗口 = 规则声明的 `return_window_days` + 运单的 `shipments.signed_at`**（选它而不是 `orders.delivered_at`，因为后者**没有任何生产写入路径**，只有 fixture 会写：读起来"同源"更漂亮，实际上会让功能在生产里静默失效）。拿不到签收时刻 → `RETURN_WINDOW_UNKNOWN` ✓（不猜 ✓），与 `RETURN_WINDOW_EXPIRED` **分开**：一个是数据缺口、一个是业务结论 ✓。**无需 migration** ✓（`return_window_days` 与 `RETURN/RETURN_REFUND` 在 V001 里早就预留 ✓）。② **两个隐藏耦合**（不修就会"测试绿、功能死"）：`needsLogisticsFacts` 原来只认 `REFUND_ONLY` ✗ → 退货会拿到 null 快照 → 每笔都被判 UNKNOWN 拒绝 ✗；**成功决策里把动作写死 `AllowedAction.REFUND_ONLY`** ✗✗ → 通过窗口的退货会**被当成退款放行** ✗✗ = 正是 US2 存在的全部理由禁止的事 ✓（**抓到它的是正例用例** ✓；当时我写的全部反例都是绿的 ✗ —— 教训：反例守"该拒的拒了"✓，正例守"该放行的放行得对"✓）。③ `LogisticsSnapshot` 增加 `signedAt`（真实时刻 ✓，布尔值算不出窗口 ✓），`LogisticsStallCalculator` 两处构造同步 ✓，`tool-contracts.md` 的 `get_logistics` 记下该字段与"缺失时返回 UNKNOWN 而非猜测"✓。**测试**：`EligibilityServiceTest` 新增四条纯函数用例（窗口内 → `RETURN_REFUND` + eligible ✓ / 超窗口 → `RETURN_WINDOW_EXPIRED` ✓ / 缺签收 → `RETURN_WINDOW_UNKNOWN` ✓ / ★ 退货规则声明停滞阈值 → `LOGISTICS_CONFLICTS_WITH_ORDER` 转人工 ✓，把"为什么不能这么配"钉进代码 ✓）；**启用** T036 那条 `@Disabled` 的集成用例 ✓（已签收 → 规则层真的放行退货 ✓）。**门禁**：`spotless:apply` → `clean verify` **BUILD SUCCESS** ✓（`Tests run: 172, Failures: 0, Errors: 0, Skipped: 0` ✓✓ —— Skipped 归零 = 那条禁用用例真的在跑 ✓；`Spotless 102 files clean` ✓ / `BugInstance 0` ✓）。**过程教训**：三次红灯**全是夹具在撒谎**✗（T038 共用 order id ✓ / 本次共用品类 ✓ / 本次把订单写成"已有售后动作"✓），没有一次是实现错 ✓ —— 区分它们的是**具名证据**（约束名 ✓、`reasonCodes` ✓），不是"看到红就改实现"✗；另有两次返工源于"没先读被调用方的签名"（`AfterSalesRule.create` 形参序 ✓、测试夹具签名 ✓、record 改动漏了测试里的构造点 ✓），已固化为规则：**动笔前先 grep 出所有要调用的签名** ✓。
- [X] T040 [US2] 实现受保护 Return Create/Status API；如要求审批，与 Refund 一样验证权威 `approvalRequestId`。→ **已完成（2026-10-06）**：① `POST /api/v1/returns`（`ReturnController` + `ReturnService` + `CreateReturnRequest`/`ReturnCommand`/`ReturnResult`）逐条镜像退款写路径：写前重校验 `EligibilityService.evaluate`、订单行锁 + 锁后幂等复查、V004 两个唯一约束按**约束名**翻译成 `IDEMPOTENCY_CONFLICT` / `DUPLICATE_AFTER_SALES`、订单投影 `RETURN_REQUESTED` + 审计同事务 ✓。② **本次只创建退货行**（用户拍板 A 方案）：`RETURN_REFUND` 的"退钱"不在这个接口发生，`RefundService` 的 `REFUND_ONLY` 守卫**一行未动** —— `aReturnInsideTheWindowIsCreatedWithAFrozenDeadlineAndNoRefundRow` 直接断言这笔写入后该订单的退款行数 **= 0** ✓。③ `V005`：`return_deadline`（受理时**冻结** = 规则窗口 + `shipments.signed_at`，窗口算术与决策层共用 `EligibilityService.returnDeadline`，只此一处）与 `return_method`（契约发布了它；V1 无行为但参与幂等指纹，因此必须落库）✓。④ 状态读面按同一聚合返回：`AfterSalesStatusResponse.returns` 从 `List<Object>` 变为 `List<ReturnResult>`，并在 `GET /orders/{orderId}/after-sales?IdempotencyKey=...` 下按 key 精确过滤 ✓（退款模块因此知道退货模块，理由与代价写在类注释里；Python 的 `AfterSalesStatus.returns` 本就是开放字典列表，故无需改契约消费端 ✓）。⑤ `approvalRequestId` 与退款同口径 fail closed `400`，且不留任何业务痕迹 ✓。⑥ **顺带修掉一个 T039 遗留的真实缺陷**：`decide` 无条件把 `refundableAmount` 塞进决策，而 `EligibilityDecision` 的不变量禁止"纯退货动作带金额" → **任何成功的纯 `RETURN` 决策都会抛 `IllegalArgumentException`（500）**，演示数据 `DEMO_HOME_30D_RETURN` 正是这种规则；现在金额与审批阈值只对会动钱的动作（`REFUND_ONLY` / `RETURN_REFUND`）生效 ✓（由 `aPureReturnInsideTheWindowIsGrantedWithoutAnAmount` 与该 HTTP 用例共同钉住）。**测试**：`ReturnHttpIntegrationTest` **9 条**（401 / 403 / 404 concealment 且消息逐字相同 / 200 + 冻结截止日 + 行 + 投影 + 审计 / 同 key 重放同一笔 / 换 key → 409 / 审批引用 → 400 / 已签收被 `REFUND_ONLY` 授予 → 422 / 超窗口 → 422）· `ReturnWriteIntegrationTest` **3 条**（**两个真实线程 + `CyclicBarrier`**：不同 key → 恰好一行且输家拿确定的 409；同 key → 同一笔；规则改版后已承诺的截止日不跟着变）✓。**门禁**：`spotless:apply` → 定点 → **`clean verify` BUILD SUCCESS**（`Tests run: 187, Failures: 0, Errors: 0, Skipped: 0` / Spotless **109 files clean / 0 needs changes** / `BugInstance 0`（新增 1 条最窄 `EI_EXPOSE_REP2` 豁免，与 T019/T021 同类且理由相同）/ JaCoCo **74 classes**）· Python 四条全绿（`ruff` / `format` **86 files** / `mypy` **48 files** / `pytest` **492 passed, 6 skipped**）✓。**契约**：`/returns` 补 `400/404/503` 与字段语义，升 **0.2.6** ✓。**过程发现（记为债）**：该契约文件里存在 **4 份互相不同的 `components` 块**（424/665/897/1134 行），T040 的 schema 改动已同步写进全部 4 份以免再添分叉；根治需单独立任务，见 `PROJECT_PROGRESS.md` 未决项 ✓。**刻意不做**：Flow Playground 不新增"退货写"步骤 —— 今天没有任何路由会走到 `/returns`（T041 才接线），此刻加一个按钮只是调试端点，不属于"会进入端到端主流程"的节点 ✓。
- [X] T041 [US2] 增加 `create_return_request` Tool，并在 graph/routing 中根据 delivered evidence 进入 Return Path。→ **已完成（2026-10-06）**：① **Tool 边界**（提交 `4b04a95`）：`CommerceClient.create_return`（`request_is_safe=False`，幂等键先做形状校验）· `CreateReturnRequest`/`ReturnResult`（**类型里没有金额字段**，与"退货行没有金额列"同源）· `create_return_request` Tool（传输失败归一为 `WRITE_TIMEOUT_UNKNOWN` + `retryable=False`）· 注册表 6 → **7 条能力** · `AfterSalesStatus.returns` 从开放字典变 typed（写后验证必须能回答"我这一行在不在里面"）✓。② **节点与路由**（提交 `06a2e57`）：`Node.RETURN_WRITE` · `REFUND_PERMITTING_ACTIONS` 收窄为 `{REFUND_ONLY}`、新增 `RETURN_PERMITTING_ACTIONS = {RETURN, RETURN_REFUND}`、`NON_REFUND_ACTIONS` → `NON_WRITE_ACTIONS`、新增 `MONEY_GRANTING_ACTIONS`（**"没有金额"只对会动钱的动作算缺口**，否则每一笔合法退货都会被 `AMOUNT_UNBOUNDED` 拒掉）· `graph.py` 条件边与拓扑声明 · `execute_return_write`（与退款同一套 write-ahead intent + 未知结果先读权威 + 同 key 预算，**核对 `returns[]`**）· `verify_return_business_state`（具名原因码 `RETURN_NOT_FOUND_FOR_IDEMPOTENCY_KEY` / `MULTIPLE_RETURNS_...` / `RETURN_ID_MISMATCH`）· `runtime.persist_intent` 从 intent 的 action **推导**节点名（否则退货写会被记在 `refund_write` 上）· `GraphDeps.writes` → `WriteTools`（同时满足两个写协议）✓。③ **有意改掉一条旧断言**：`test_graph_routing.py` 原本把 `RETURN_REFUND` 钉在退款写节点上 —— 那正是要从根上修掉的行为；现在改为 `RETURN/RETURN_REFUND → RETURN_WRITE`，并写明"这是 US2 拆分的可执行形式" ✓。**门禁**：Python 四条全绿（`ruff` / `format` **87 files** / `mypy` **48 files** / `pytest` **498 passed, 6 skipped**）✓；本 T 未改 Java，故未重跑 `mvnw verify`（与 T022/T029/T030 的既有口径一致）。**已知缺口（未做，不夸大）**：Flow Playground 还没有"退货写"步骤 —— 5173 live 验收本环境做不到，留待用户本机那一轮一起补 ✓。
- [X] T042 [US2] 增加 Delivered/Return Eval Case 与 forbidden-direct-refund assertion。→ **已完成（2026-10-06）**：① **判分器接受退货事实**（`eval/scorers/business_state.py`）：新增 `ReturnFacts`、`Expectation.returns_for_order` / `return_statuses`，签名变为 `score_business_state(expectation, observed, *, returns=())`；模块 docstring 写明**为什么"零断言"必须配机制断言** —— `refunds == 0` 在一个什么都没做的 run 上同样成立，而那恰好是 US2 最需要证明的事 ✓。② **runner 的两条机制断言**（`eval/runner.py`）：`returnToolRequired`（trace 里确实出现过 `create_return_request`）与 `refundToolForbidden`（**从未**出现 `create_refund_request`）；新增 `return_rows(...)`（用**业务角色**读权威存储，不经 Agent API）与 `tool_call_count(...)`；另支持 **per-case `orderId`**（一个数据集里现在有两个世界，用全局 `--order-id` 已经不成立）✓。③ **夹具改成相对时间**（用户拍板 A）：新 registry case `return-delivered-001`（fixtureVersion `t042-return-delivered-001-v1`）+ `FixtureLoader.seedDeliveredReturnCase()`，`signed_at = clock.instant() - 3 天`，配一条 `RETURN_REFUND` / 窗口 7 天 / `logistics_stalled_hours = NULL`（退货规则不得声明停滞阈值，否则已签收运单会命中冲突检查转人工）的规则；老夹具的绝对时间戳**抽成命名常量** `LEGACY_DELIVERED_AT`，并在注释里写明它为什么会腐烂（配上 7 天窗口，2026-09-19 就已过期）✓。④ **新数据集** `eval/datasets/dev/us2_delivered_return.yaml`：结果层 `returnsForOrder: 1` + `refundsForOrder: 0`，机制层两条 ✓。**测试**：`eval/tests/test_us2_return_scoring.py` **5 条**（专门钉住两种"说谎方式"：少一行退货却因为退款侧为空而通过、被禁止的退款行被忽略）→ `pytest eval/tests` **10 passed** ✓；Java **`clean verify` BUILD SUCCESS**（`Tests run: 187, Failures: 0, Errors: 0, Skipped: 0` / Spotless **109 files clean / 0 needs changes** / `BugInstance 0` / JaCoCo 74 classes）✓。**真实数字（2026-10-06 本机实测：Java `dev,eval` + 真实 Agent + 真实 LLM）**：`python eval/runner.py --dataset eval/datasets/dev/us2_delivered_return.yaml` → **`{"pass": 1}`**、`[pass] us2-delivered-return: business state matches the case` ✓✓ —— 结果层（`return_requests` 恰好 1 行、`refund_requests` **0 行**）与机制层（`create_return_request` 发生过、`create_refund_request` **从未**发生）**四条同时成立**，run 以 `COMPLETED` 收尾 ✓。**前两次真实运行都是 fail，而且两次都是夹具的错、产品是对的**（本次最有价值的证据）：
  · 第一次 `WAITING_USER` + 零写入 —— 夹具同时给了 customer-001 一张未签收订单和一张已签收订单 → 解析层看到两个候选就**拒绝猜**、去澄清（正确的 US3 行为，错的 case）→ 修法：退货 case **只造自己的世界**，不再叠加基础世界 ✓；
  · 第二次 `COMPLETED` + 零写入 —— 演示数据里的 `DEMO_DELIVERED_7D_RETURN`（category 通配）仍在库里，与我的 `RETURN_DELIVERED_WINDOW` **同时匹配** order-003 → 按设计判 `CONFLICTING_RULES` 转人工（具名证据：查库出来的两条启用规则都命中）→ 修法：eval reset 改为**清空 `after_sales_rules`** —— "重置到已知基线"的语义就是它不该继承自己没选择的政策，而不是只删本 loader 造的那两条 ✓。
  **可迁移的结论**：一条从没真跑过的 Eval case，第一次跑几乎一定先暴露**夹具的错**；而"产品正确地拒绝了"与"功能坏了"在报告里长得一模一样 —— 区分它们的只有**具名证据**（库里的规则行、trace 里的工具名），不是状态码 ✓。**过程记录**：eval 侧的第一个提交（`a38c326`）**曾误直接提交到 dev**（当时仍在 dev 上、未建功能分支），经用户确认**不重写历史**、留在 dev；其余部分在 `feat/us2-delivered-return-eval` 上完成 ✓。

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
- [ ] T051 [US4] 新建 `commerce.approval_requests` schema 与 Entity/Repository：`V005__approval_schema.sql`、`approval/`；同步扩展 T014 fixture reset 清理 approval state。
- [ ] T052 [US4] 实现 Approval Create/List/Decision API；List/Decision 要求 `APPROVER` role 并写 Audit。
- [ ] T053 [US4] 实现 `request_human_approval` Tool，返回权威 `approvalRequestId`，并进入 `WAITING_APPROVAL`；Agent 不得生成 approval token/status。
- [ ] T054 [US4] 实现 owner-authorized Agent Resume；恢复前重新读取 Java Approval 状态并验证 run/order/action/amount binding。
- [ ] T055 [US4] 实现最小 Approval Center：展示 order/action/amount/risk reason/evidence 与 Approve/Deny。
- [ ] T056 [US4] 增加 high-risk、denied、cross-bound approval id、attempted self-approval Eval Case。

---

## Phase 7：US5 无法自动处理时安全转人工（P2）

- [ ] T057 [P] [US5] 编写 retry budget、no-progress loop、dependency timeout、`MANUAL_REVIEW`、safe stop、escalation Python Test。
- [ ] T058 [P] [US5] 编写 SupportTicket create/ownership/audit Java Test。
- [ ] T059 [US5] 新建 `commerce.support_tickets` schema 与 Entity/Repository；只保存结构化 evidence summary/reason code；同步扩展 T014 fixture reset 清理 support-ticket state。
- [ ] T060 [US5] 实现受保护 SupportTicket Create API。
- [ ] T061 [US5] 实现 error contract normalization、no-new-evidence detection、max-step enforcement、`escalate_or_safe_stop` Node。
- [ ] T062 [US5] 实现 `create_support_ticket` Tool，并附带现有 structured evidence/run id。
- [ ] T063 [US5] 增加 dependency failure、conflicting state、max-step、manual-review Eval Case。

---

## Phase 8：US6 政策检索与解释（P2 / 可延期）

该阶段不得阻塞 Portfolio MVP。如果 US1–US4、Safety、Eval 尚未稳定，可以整体延期。

- [ ] T064 [P] [US6] 编写 effective-date、citation metadata、expired/conflict policy、retrieval prompt-injection Test。
- [ ] T065 [US6] 如确认需要向量检索，首次创建 `knowledge/policies/`，启用 pgvector extension，并创建 `policy.policy_documents` / `policy.policy_chunks`；否则允许先使用版本化 Policy Lookup，且不启用 vector extension。
- [ ] T066 [P] [US6] 创建 synthetic AfterSalesPolicy 文档：general refund、logistics exception、electronics return、manual-review。
- [ ] T067 [US6] 实现 Policy Ingestion/Chunking/Embedding（仅启用 Vector Retrieval 时）。
- [ ] T068 [US6] 实现 metadata-filtered Policy Retrieval，返回 document code/version/effective date/section/score/conflict flags。
- [ ] T069 [US6] 实现 `policy_search` Tool 与 Citation Rendering，明确阻止 Policy Text 修改 tool allowlist、auth、eligibility、amount、approval。
- [ ] T070 [US6] 增加 policy citation、expired/conflict、retrieval injection Eval Case。

---

## Phase 9：Polish / Eval / Reproducibility

- [ ] T071 实现 CLI/file-first Eval Runner：调用 Reset Contract、执行 Agent、采集 final business state / tool trace / latency / token，输出 JSON 到 `eval/reports/`；验收 reset completeness（副作用写入后再次 reset 必须恢复干净状态），并对 destructive reset 使用独立 test/eval 数据库做 fail-fast guard。
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
