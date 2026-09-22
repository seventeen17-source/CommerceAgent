# CommerceAgent Project Progress

> 这是项目的唯一阶段导航文件。每次开始开发先看这里，再去 `tasks.md` 找当前阶段任务。

## 当前状态

- **当前 Phase**：Phase 2 — Foundational ✅ 收口
- **当前 Tasks**：T020（Phase 3 — US1 MVP）
- **已完成**：
  - T001 — 根项目入口与当前需要的目录已建立；`eval/`、`knowledge/policies/` 不为空建目录，改由首次产生真实内容的对应任务创建
  - T002 — Spring Initializr 生成 `commerce-backend/`（Java 21 / Spring Boot 4.1.1），`mvnw.cmd test` BUILD SUCCESS
  - T003 — `uv init` 生成 `agent-service/`、`uv.lock`（58 包）；`uv run python --version` → `Python 3.13.14`，导入 smoke 通过
  - T004 — Vite 生成 `web/`、`npm install` 完成、`npm.cmd run build` 成功产出 `dist/`
  - T005 — PostgreSQL（`pgvector/pgvector:0.8.6-pg18` 镜像）与三个逻辑 schema、三个独立角色；**`agent_app` 读 `commerce.*` 被数据库拒绝**（实测）；T005 不启用 `vector` extension，是否启用留给 US6/T065
  - T006 — Java 侧 Spotless 3.10.2（palantirJavaFormat）+ SpotBugs 4.10.4.1 + JaCoCo 0.8.15；Python 侧 ruff 0.16.8 + mypy 2.3.1。`mvnw verify` **BUILD SUCCESS**；`ruff check` / `ruff format --check` / `mypy app` 全部通过
  - T007 — `application.yml`（含 dev profile，应用身份 `commerce_app` / 迁移身份 `migrator` 分离）、`application-test.yml`（数据源由 Testcontainers 注入）、`app/config/settings.py`。实测 `mvnw spring-boot:run` **Started CommerceBackendApplication in 4.538 seconds**，Flyway 以 `migrator` 身份把 history 表建在 `commerce` schema
  - T008 — `V001__core_schema.sql` 创建 9 张核心表并建立约束/索引；本地 `mvnw.cmd verify` **BUILD SUCCESS**；`infra/postgres/verify-t008.sql` 返回 **`T008_ACCEPTANCE_OK`**；`agent_app` 对 `commerce.*` 无权限，`commerce_app` / `agent_app` 各自在所属 schema 具备所需权限；`vector` extension 未启用
  - T009 — `user/`、`order/`、`logistics/` 共 5 个 JPA Entity + 5 个 Repository；`@Version` 乐观锁与 ownership 不可变由映射层表达；新增 `OrderConcurrencyGuaranteesTest` **用可执行测试证明**"乐观锁防丢失更新、唯一约束防重复插入"；`mvnw verify` → **Tests run: 7, Failures: 0, Errors: 0 / BUILD SUCCESS**
  - T010–T014 — 见「Phase 2 — 当前执行顺序」第 3–7 项的验收证据（`AfterSalesRule` 持久化 / JWT role-aware principal / 统一 Error Envelope / 结构化 Audit Writer / dev-eval Fixture Loader）
  - T015 — 显式 `AgentState`（`agent-service/app/agent/state.py`）：Pydantic 状态 schema + `PrincipalRole`/`RunStatus`/`WriteStatus`/`VerificationStatus` 四个枚举，`extra="forbid"` 拒绝未声明字段（含 raw credential），model validator 对 step/retry budget fail closed；Python 门禁四条命令全部通过：`ruff check` **All checks passed**、`ruff format --check` **7 files**、`mypy app` **Success 5 files**、`pytest -q` **11 passed**
  - T016 — 类型化 Java API Client（`agent-service/app/clients/`：`auth.py` / `models.py` / `errors.py` / `identity.py` / `commerce_client.py`）+ Java `TraceIdFilter` 收紧 + `FixtureLoader` advisory lock 修复；Java `mvnw.cmd verify` → **BUILD SUCCESS**（Tests run: 52, Failures: 0, Errors: 0；Spotless 64 files clean / 0 needs changes；SpotBugs BugInstance 0）；Python 四条门禁全绿（`ruff check` **All checks passed**、`ruff format --check` **17 files**、`mypy app` **Success 11 files**、`pytest -q` **86 passed**）。验收证据见「T016 验收证据」
  - T017 — Run/Checkpoint/Structured Tool Trace 持久化：`agent-service/app/trace/`（`checkpoint.py` / `db.py` / `store.py` / `retention.py` / `errors.py`）+ `app/security/secrets.py`（持久化边界护栏）+ `V002__agent_run_checkpoint.sql`；Java `mvnw.cmd verify` → **BUILD SUCCESS**（Tests run: 61, Failures: 0, Errors: 0；Spotless 65 files clean / 0 needs changes；SpotBugs BugInstance size 0；JaCoCo 42 classes）；Python 四条门禁全绿（`ruff check` **All checks passed**、`ruff format --check` **30 files**、`mypy app` **Success 19 files**、`pytest -q` **195 passed, 13 skipped**，其中 **21 个真实 PostgreSQL 集成用例**证明并发 resume 只产生一个赢家。验收证据见「T017 验收证据」
  - T018 — FastAPI 认证 / Principal / Run Ownership / Run 骨架接口：`app/security/credentials.py`（只证明"合法"不证明"是谁"）、`app/security/dependencies.py`、`app/api/runs.py`（6 个端点，认证声明在 router 级）、`app/main.py`（`create_app` 工厂 + lifespan 单例）、`app/trace/store.py` 增补 `get_run_for_owner`（owner 进 SQL 谓词）、`web/vite.config.ts`（dev proxy + rewrite）、Flow Playground 步骤 08–10（Run 创建、查询与 events 真实控件）、`scripts/mint_dev_token.py`、`scripts/run_chain_check.py`；Python四条门禁全绿（`ruff check` **All checks passed**、`ruff format --check` **39 files**、`mypy app` **Success 24 files**、`pytest -q` **234 passed, 13 skipped**）；Web `npm.cmd run build` 成功、`npm.cmd run lint` 0 warnings/0 errors。**5173 真实端到端流转测试通过**（见「T018 验收证据」）
  - T019 — ownership-scoped order/logistics read 与权威 stall calculation：`order/OrderService.java`（ownership 唯一判定入口 + 订单列表/详情读模型 + cross-owner 内部安全审计）、`logistics/LogisticsService.java`、`logistics/LogisticsStallCalculator.java`、`common/time/ClockConfig.java`；新测试 `OrderLogisticsIntegrationTest.java` **14 个用例**；**契约按 404 concealment 口径统一**（`commerce-api.openapi.yaml` 给 logistics 补 `404`、两个 read 端点的 `403` 明确只表示角色/能力不足，`error-contracts.md` 删除 `ORDER_FORBIDDEN`）。Java `mvnw.cmd verify` → **BUILD SUCCESS**（Tests run: **75**, Failures: 0, Errors: 0；Spotless 73 files clean / 0 needs changes；SpotBugs BugInstance **0**（新增 1 条最窄 exclude，见证据）；JaCoCo 50 classes）。验收证据见「T019 验收证据」
- **当前优先任务**：T020 — deterministic eligibility 与拒绝模型覆盖 amount/eligibility 的 Java Test（`EligibilityServiceTest.java`）
- **下一 Gate**：T019–T035 打通 Web → Agent → Java → DB → exactly one RefundRequest → verified result → structured trace
- **当前 Blocker**：无（T016 前置 contract hardening 已复验通过，证据见「T016 验收证据」）
- **环境事实（重要）**：
  - 本机 PowerShell 执行策略为默认 `Restricted`，`npm` 会命中被拦的 `npm.ps1` → **前端命令一律用 `npm.cmd` / `npx.cmd`**
  - 本机 `core.autocrlf=true`；`infra/` 下的脚本与 `.env*` 已由根 `.gitattributes` 钉为 LF（否则容器内执行会 `bad interpreter`）
  - 数据库容器 `commerceagent-postgres`，宿主端口 **5432**，并仅绑定 `127.0.0.1:5432`；Adminer 仅绑定 `127.0.0.1:8081`
  - 原 `opspilot-db` 已废弃并移除，其数据卷 `opspilot_agent_pgdata` 保留未删
  - 启动数据库：`docker compose -f infra/docker-compose.yml up -d`（首次可 `cp .env.example .env` 覆盖默认值）
  - Java 侧两条命令：`mvnw.cmd spotless:apply` 修复格式；`mvnw.cmd verify` 跑 compile + test + spotless check + SpotBugs + JaCoCo
  - Testcontainers PostgreSQL 已固定为 `postgres:18`，避免 `latest` 漂移破坏可复现性
  - Python 侧验收命令：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy app`、`uv run pytest -q`（四条全绿才算通过）
  - **本沙箱下 `uv run` 无法写 `%LOCALAPPDATA%\uv\cache`**，等价替代：`agent-service\.venv\Scripts\python.exe -m ruff|mypy|pytest ...`
  - Python 集成测试默认连 `127.0.0.1:5432`（**不要写 `localhost`**：本机解析到 `::1` 在前，而容器只发布 IPv4，每次连接会等满 `connect_timeout`）；可用 `AGENT_TRACE_TEST_DATABASE_URL` 覆盖；连不上时用例 **skip 而非 fail**
  - Java Testcontainers 需要 Docker 命名管道（在工作区之外）：受限沙箱下 `mvnw verify` 会以 `Could not find a valid Docker environment` 失败，这**不是代码问题**
- **未决项**：
  - `.specify/feature.json` 仅为本地 Spec Kit 活动 feature 状态，不提交；运行 Spec Kit 前本地确认解析到 `specs/002-commerce-after-sales-agent`
  - T015 后续跨服务审查又发现并已在 `foundation/t016-contract-hardening` 处理：① OpenAPI 的 Java-owned enum 不应让 T016 生成封闭消费端枚举；② `ruleVersion` 契约误写为 string；③ Python 无法仅凭当前 JWT 得到权威 role，因此增加 Java `GET /api/v1/me`；④ Evidence/Verification 开放字典增加递归敏感信息拒绝。T017 另明确要求并发 resume 使用 row lock/CAS/version 防分叉。
  - T015 的 3 个评审发现已全部在 T015 内处置完毕（详见 `docs/devlog/2026-09-18.md` 的「T015 review findings 处置结果」）：②③ 采纳并落地，① 经判断**拒绝**并把"跨服务取值策略"写进 `state.py`（远程拥有的值域不镜像成 `StrEnum`，未知值受控降级为 `SAFE_STOP`）
  - **T017 前置：AgentState 敏感信息拦截覆盖不足 —— 已在 T017 内关闭**。原状：拦截只挂在 `EvidenceItem.data` / `VerificationOutcome.details` 两个字段上，16 个自由文本字段注入 32 次仅拦 2 次。处置：规则移入 `app/security/secrets.py` 作为**持久化边界**规则（模型构造 + 落盘前各调一次，同一个函数），并新增遍历 `AgentState.model_fields` 的 meta-test 使新增字段自带用例；`_BEARER_PATTERN` / `_JWT_PATTERN` 先收紧（结构化判定）再扩大覆盖。证据见「T017 验收证据」与 `docs/devlog/2026-09-21.md`。
  - 根 `.gitignore` 建议补 `.mypy_cache/`、`.ruff_cache/`（当前靠工具默认行为兜底）
- **Skill 规则**：`main` / 功能分支保留 Spec Kit 初始化生成的 `.agents/skills/speckit-*`；`project-coding-tutor` 等自定义 Skill 源码统一维护在 `skills_` 分支或安装为本地/全局 Skill
- **明确延期**：US6 Policy/RAG、独立 Eval Dashboard、MCP、Multi-Agent、Kafka、Kubernetes、花哨 UI

## 阶段总览

| Phase | 目标 | Tasks | Gate | 状态 |
|---|---|---|---|---|
| 0 | 设计冻结 | — | 002 Spec / Plan / Tasks / Contracts 已对齐 | ✅ Complete |
| 1 | 官方项目脚手架 | T001–T007 | Java / Python / Web 可启动，PostgreSQL 基础配置就绪 | ✅ Complete（T001–T007 ✅） |
| 2 | Foundation | T008–T018 | AgentRun / Auth / DB boundary / Trace 基础能力可用 | ✅ Complete（T008–T018 ✅） |
| 3 | US1 MVP | T019–T035 | 物流异常 → eligibility → refund → verification 真实 E2E 跑通 | 👉 Current（T019 ✅，当前 T020） |
| 4 | Agent Value | T036–T048 | 同类请求可因证据走退货 / 澄清等不同路径 | ⬜ |
| 5 | HITL | T049–T056 | 高风险动作等待权威审批并可恢复执行 | ⬜ |
| 6 | 安全降级 | T057–T063 | 依赖失败 / 规则冲突时 Safe Stop 或转人工 | ⬜ |
| 7 | Policy / RAG | T064–T070 | 政策证据可检索引用，但不掌握资金授权 | ⬜ Optional/P2 |
| 8 | Eval & Portfolio | T071–T083 | Eval、CI、Docker、README、Demo、真实指标完成 | ⬜ |

## Phase 1 — 完成记录

1. ✅ 拉取最新 `main` 并确认工作区干净
2. ℹ️ `.specify/feature.json` 仅为本地 Spec Kit 状态；不提交到仓库。运行 Spec Kit 前本地确认活动 feature 为 `specs/002-commerce-after-sales-agent`
3. ✅ 创建分支：`setup/official-scaffolds`（已并入 main）；T005 起使用 `setup/postgres-infra`
4. ✅ T001：建立当前阶段真实需要的项目入口/目录；`eval/` 与 `knowledge/policies/` 延迟到首次有真实内容时创建，不提交空目录
5. ✅ T002：Spring Initializr 生成 `commerce-backend`（Java 21 / Spring Boot 4.1.1；`mvnw.cmd test` BUILD SUCCESS）
6. ✅ T003：`uv init` 初始化 `agent-service`（Python 3.13.14，`uv.lock` 58 包）
7. ✅ T004：Vite 生成 `web`（`npm.cmd run build` 成功产出 `dist/`）
8. ✅ T005：PostgreSQL + 逻辑 schema + 独立 DB role（`infra/docker-compose.yml`、`infra/postgres/initdb/`、`.env.example`、`.gitattributes`）；保留 pgvector-capable 镜像但不提前启用 extension
9. ✅ 三个脚手架最小 build / smoke test：Java ✅ / Web ✅ / Python ✅；**数据库连通性已由 T007 实测验证**
10. ✅ T006–T007：Java/Python lint 配置、dev/test/eval 配置（`mvnw verify` BUILD SUCCESS；`spring-boot:run` 启动成功）

## Phase 1 完成标准

只有同时满足以下条件，才进入 Phase 2：

- [x] Java 工程由 Spring Initializr 官方生成
- [x] Maven Wrapper 可用
- [x] Java 版本与 Plan 一致（Java 21；Spring Boot 经决策由 3.5.x 升为 4.1.1）
- [x] Python 工程由 `uv init` 生成
- [x] Python 版本与 Plan 一致，保留 `uv.lock`
- [x] React + TypeScript 工程由 Vite 生成
- [x] 三个工程最小启动 / build 成功
- [x] PostgreSQL / Docker Compose 基础环境可启动（实测 healthy；含 schema 归属与 role 边界验证）
- [x] 没有提前加入 US6 / MCP / Multi-Agent 等非当前依赖；`vector` extension 未在 T005 启用（重置数据卷后实测 `pg_extension` 中为 0）
- [x] Git diff 只包含预期脚手架和基础配置（Phase 1 收尾后 `git status` 干净）
- [x] 当天 `docs/devlog/YYYY-MM-DD.md` 已记录真实进展、问题、决策和 Git 证据（2026-09-16 记 T001/T002；2026-09-17 记 T003–T007）

> 「三个工程最小启动 / build 成功」的实测依据：Java `mvnw verify` BUILD SUCCESS（含 Testcontainers 起真实 PostgreSQL）；Web `npm.cmd run build` 产出 `dist/`；Python `uv run python --version` → 3.13.14、`mypy app` 通过且 `settings` 可加载。Python 的应用入口（`app/main.py`）属 T018。
> 「Git diff 只包含预期脚手架和基础配置」已验证：Phase 1 收尾后工作区干净，改动全部落在 `2a5dbde`（T006 Java）/ `2d204a2`（T006 Python）/ `f371be7`（T007 配置）/ `d47a121`（文档）四个提交内。

## Phase 2 — 当前执行顺序

1. ✅ T008：初始 Flyway migration（核心业务表 + Agent Run/Trace 表）
2. ✅ T009：User / Order / OrderItem / Shipment / LogisticsEvent JPA Entity/Repository
3. ✅ T010：AfterSalesRule 持久化（`mvnw.cmd verify` → Tests run: 10, Failures: 0, Errors: 0 / BUILD SUCCESS）
4. ✅ T011：JWT / role-aware principal（本地 `mvnw.cmd verify` → BUILD SUCCESS；Spotless/SpotBugs 均通过）
5. ✅ T012：统一 Error Envelope（本地 `mvnw.cmd verify` → Tests run: 22, Failures: 0, Errors: 0, Skipped: 0 / BUILD SUCCESS；Spotless、SpotBugs 均通过）
6. ✅ T013：结构化 Audit Writer（本地 `mvnw.cmd verify` → BUILD SUCCESS；测试、Spotless、SpotBugs 均通过）
7. ✅ T014：dev/eval fixture loader（本地 `mvnw.cmd verify` → BUILD SUCCESS；35 tests、Spotless、SpotBugs 均通过）
8. ✅ T015：显式 `AgentState`（Python 门禁四条命令全部通过：`ruff check` / `ruff format --check` / `mypy app` / `pytest -q` → 11 passed）
9. ✅ T016：类型化 Java API Client（Java `mvnw.cmd verify` → **BUILD SUCCESS**，Tests run: 52；Python 四条门禁全绿 → 86 passed）
10. ✅ T017：Run/Checkpoint/Tool Trace 持久化（Java **BUILD SUCCESS** 61 tests；Python 四条门禁全绿 → 195 passed / 13 skipped，含 21 个真实数据库集成用例）
11. ✅ T018：FastAPI 认证 / principal / run ownership / run 骨架接口（Python 四条门禁全绿 → 234 passed；Web build + lint 通过；**5173 端到端流转实测通过**）—— Phase 2 收口
12. 👉 T019–T035：US1 物流异常退款 MVP（T019 ✅ 读面与停滞口径已钉死；当前 T020）

### T008 验收证据

- `V001__core_schema.sql` 已创建 `commerce.users`、`orders`、`order_items`、`shipments`、`logistics_events`、`after_sales_rules`、`audit_logs`、`agent.agent_runs`、`agent.tool_executions`
- `mvnw.cmd verify`：用户本地复验 **BUILD SUCCESS**
- `infra/postgres/verify-t008.sql`：用户本地复验返回 **`T008_ACCEPTANCE_OK`**
- PostgreSQL / Adminer 对宿主机均仅绑定 `127.0.0.1`
- Flyway 测试检查的是 **V001 存在且 success=true**，不再错误要求“最新 migration 必须永远是 V001”
- Testcontainers 固定 `postgres:18`，避免 `latest` 漂移

### T009 验收证据

- **最终本地复验通过**：review 收紧 `Shipment.order_id` 映射并补充 Shipment 乐观锁测试后，重新执行 `mvnw verify` → **Tests run: 7, Failures: 0, Errors: 0 / BUILD SUCCESS**；完整 verify 已通过
- **订单乐观锁已实测生效**：`OrderConcurrencyGuaranteesTest.staleUpdateIsRejectedByOptimisticLocking` —— 两个读者拿到同一快照，先写者成功且版本号自增，后写者被 `ObjectOptimisticLockingFailureException` 拒绝，且先写结果未被覆盖
- **Shipment 乐观锁已实测生效**：`staleShipmentUpdateIsRejectedByOptimisticLocking` 对 `Shipment.version` 做 stale-update 验证，并已包含在最终 7 个通过的测试中
- **唯一约束真的在拦重复**：`duplicateShipmentForSameOrderIsRejectedByUniqueConstraint` —— 同一订单第二条运单被 `DataIntegrityViolationException` 拒绝（两条新记录的版本号相同，`@Version` 在此毫无作用）
- **映射与数据库一致由 `ddl-auto: validate` 保证**：本次它抓出并修正了 `CHAR(3)` 与 `TEXT` 两处类型不匹配（实体如实声明，**未改动已执行的 V001**）
- **两个状态枚举明确不是数据库约束**：`shipments.status` / `orders.after_sales_status` 在库中无 CHECK，枚举只是 Java 侧护栏；取值为 V1 最小集，待 T024/T026 扩展
- **Post-review hardening 已本地复验通过**：`Order.createdAt` / `User.createdAt` 增加 Hibernate `@Generated(INSERT)`，`DatabaseGeneratedValuesTest` 验证写后立即可读；重复 Shipment 测试使用 `saveAndFlush` 并同时断言 SQLState `23505` 与约束名 `shipments_order_id_key`，避免因其他完整性错误产生 false positive；最终 `mvnw verify` → **Tests run: 8, Failures: 0, Errors: 0 / BUILD SUCCESS**

### T016 验收证据

- **Java `mvnw.cmd verify` → BUILD SUCCESS**（本机实测 2026-09-20 19:48：Tests run: 52, Failures: 0, Errors: 0, Skipped: 0；Spotless 64 files clean / 0 needs changes；SpotBugs BugInstance size 0 / Error size 0；JaCoCo 分析 42 classes）
- **Python 四条门禁全绿**：`ruff check` **All checks passed** / `ruff format --check` **17 files** / `mypy app` **Success 11 files** / `pytest -q` **86 passed**
- **交付内容**：`agent-service/app/clients/` 五个模块 —— `auth.py`（`AuthContext`）、`models.py`（读/评估面响应模型）、`errors.py`（两类远端失败 + 两个本地前置失败）、`identity.py`（wire role → `PrincipalRole` 的 fail-closed 映射）、`commerce_client.py`（httpx 传输、per-call Bearer、timeout、trace 关联、响应校验）
- **端点范围**：只做读/评估面（`/me`、`/orders`、`/orders/{id}`、`/orders/{id}/logistics`、`/after-sales/eligibility`）；写面（`/refunds`、`/returns`、`/approvals`）留给 T026/T038
- **"答了" 与 "没答" 是两种类型**（可执行证据）：`CommerceApiError.blind_retry_allowed == envelope.retryable`；`CommerceTransportError.blind_retry_allowed == request_was_safe`。`request_was_safe` 由**操作语义**决定而非 HTTP 方法 —— `POST /after-sales/eligibility` 是确定性、无副作用的评估，必须保持可安全重试；用 `method == "GET"` 推导会把这个读接口的 retry budget 砍掉
- **client 自身从不重试**：`retryable=true` 不是重试授权，retry budget 属于 Tool 层；client 里放重试循环会把 unknown-outcome 藏起来，让唯一有权决定处置的层看不见它
- **契约外的错误响应按"没有答案"处理**：即使是 5xx，只要 body 不符合 error envelope，就归为 `CommerceTransportError`（结果未知）而非"已知失败"——裸状态码不能证明写操作没提交，把它当"已知"会为盲目重试发放许可
- **前向兼容**：`allowedAction` 与 wire `role` 都是开放字符串；Java 新增取值不会变成解析失败，未知 role 由 `identity.resolve_principal` 显式拒绝（`UnknownPrincipalRoleError` → `ACCESS_DENIED`）而不是猜一个默认角色
- **token 不可进 prompt 由类型保证**：`SecretStr` 的 `repr`/`str` 脱敏，且 `AuthContext` 刻意不含 `user_id` —— 身份只能来自 Java `GET /me`，无法被断言；token 里的 CR/LF 也在构造期被拒（否则可注入额外 HTTP 头）
- **模型输出的 `order_id` 不能改写 URL**：`_safe_path_segment` 在发请求前拒绝含 `/`、`?`、`#`、空白的路径段（`UnsafeRequestParameterError`，本地失败、无未知结果）
- **实测缺陷修复（活体冒烟发现）**：
  - `trust_env=False`：httpx 会从环境**及 Windows 注册表**解析代理，实测 `127.0.0.1:7892` 接管了 `http://localhost:8080`、收到转发的 Bearer token、并返回契约外的 502。代价已写明：`trust_env=False` 同时不再读 `SSL_CERT_FILE` / `SSL_CERT_DIR`
  - `FixtureLoader` advisory lock：`pg_advisory_xact_lock` 返回 `void` 却按 `Boolean.class` 取值，驱动抛 "cannot cast to boolean"，导致 dev profile 下 `spring-boot:run` 起不来（`DevelopmentFixtureInitializer` 是 `@Profile("dev")`，`mvnw verify` 从不覆盖该路径，故该缺陷从 T014 存活至今）；已补直接调用 loader 的回归测试
- **Java `TraceIdFilter` 已收紧**：只接受格式/长度校验通过的入站 correlation id，否则生成新的 server trace id；新增 15 个 `TraceIdFilterTest` 用例
- **T016 post-review hardening**：错误响应现在与成功响应共用 `_correlate()` 产出的已校验 correlation id；JSON error envelope 的 `traceId` 不再覆盖最终 `CommerceApiError.trace_id`。用户随后已反馈 Python 四条门禁重新全绿，但当时未记录新的 pytest 总数，因此这里不伪造统计值。2026-09-21 又补充 `test_client_auth.py`，直接钉死 credential ≠ identity、CR/LF/whitespace 拒绝、SecretStr 脱敏、额外 `user_id/role` 拒绝；**这一个新提交尚需再跑一次 Python 四条门禁作为最终封账证据**。

### T017 验收证据

- **Java `mvnw.cmd verify` → BUILD SUCCESS**（本机实测 2026-09-21：Tests run: **61**, Failures: 0, Errors: 0, Skipped: 0；Spotless 65 files clean / **0 needs changes**；SpotBugs **BugInstance size 0**；JaCoCo 分析 42 classes）。其中新增 `AgentRunCheckpointSchemaTests` **9 个用例**，`CoreSchemaMigrationTests` 3 个用例仍通过。
- **Python 四条门禁全绿**：`ruff check` **All checks passed** / `ruff format --check` **30 files** / `mypy app` **Success 19 files** / `pytest -q` **195 passed, 13 skipped**。
- **交付内容**：
  - `agent-service/app/trace/` 五个模块 —— `checkpoint.py`（记录 + 生命周期集合 + 记录层护栏）、`db.py`（注入式连接工厂 + `dict_row` + 显式事务）、`store.py`（`PostgresRunStore` / `RunStore` 契约）、`retention.py`（`RetentionPolicy` + `sweep_terminal_runs`）、`errors.py`（8 个类型化失败 + `ResumeRefusalReason`）
  - `agent-service/app/security/secrets.py` —— **唯一**的持久化边界敏感信息规则
  - `V002__agent_run_checkpoint.sql` —— `version` / `checkpoint_compacted_at` / 终态-完成时间约束 / `status+started_at` 索引 / `agent.agent_checkpoints`
- **并发 resume 有可执行证明**（不是设计说明）：`test_two_concurrent_resumes_of_one_checkpoint_produce_exactly_one_winner` 用**两个真实线程 + `threading.Barrier`** 对同一旧 checkpoint 同时 resume，断言结果集合恰为 `["refused:ALREADY_CLAIMED", "won"]`、run 只前进一个版本、且只多出一条 checkpoint。**没有用内存假实现**：内存 double 的"锁"是它自己实现的，测它只能证明它和自己一致。
- **为什么"行锁"和"version"都要**：`SELECT ... FOR UPDATE` 只把并发请求**串行化**；没有 version 比较时，第二个请求阻塞结束醒来后仍会按旧快照继续执行 —— 那正是 T017 禁止的分叉。锁让检查不竞态，version 比较才**发现过期**。第 5 步 `UPDATE ... WHERE run_id=? AND version=?` 是纵深防御。
- **隔离级别用默认 `READ COMMITTED`（有理由）**：`REPEATABLE READ` 会让第二个事务拿到 serialization failure，调用方就无法区分"基础设施报错"和"别人已抢到这个 resume"，恰好丢掉 T017 要保留的赢家/输家信息。
- **行与 payload 的漂移在本 store 内不可表达**：行值与其 `state_json` 由**同一个 dict、同一条 UPDATE** 写入；`test_checkpoint_payload_matches_the_row_it_was_written_with` 直接断言 `state.status` 与行一致。
- **secret-guard 缺口已关闭**（T015 遗留，devlog 2026-09-18 记录未实现）：`tests/unit/test_state_secret_guard.py` **meta-test 遍历 `AgentState.model_fields`** 逐字段注入；**持久化边界层无豁免清单**（全字段必须拒绝），模型构造层单独断言且不冒充覆盖率。原先"逐字段白名单 2/16"的问题根源是**白名单会随字段增长腐烂**，现在新增字段自带用例。
- **检测规则用结构而非长度**（先收紧再扩覆盖）：旧 `bearer\s+[^\s,;]+` 对普通英文**误报 6/6**；新规则要求 Bearer 后为凭据形状、JWT 前两段必须**解码成 JSON object**。`a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8` 这类 trace-id 不再误报，真 JWT 仍命中。**删除了一个凭空猜的 agent-token 正则**（本项目不存在该格式，只会制造误报）。
- **集成测试抓到 3 个 mock 发现不了的真问题**：① `create_run` 漏写行上的投影列（`resolved_order_id` 实际为 `NULL`）；② Java 测试里 `started_at`（数据库时钟）与 `completed_at`（JVM 时钟）**跨时钟比较**被约束拒绝；③ `localhost` 解析到 IPv6 而容器只绑 `127.0.0.1`，每次连接先等满 5s 超时再回落（实测 **5.03s vs 0.013s**），测试默认 URL 改 `127.0.0.1` 后 21 个集成用例从"分钟级"降到 **1.55s**。
- **retention 策略**（`retention.py`）：`COMPLETED`/`ESCALATED` 保留 7 天后清 payload 与 trace；`FAILED`/`SAFE_STOP` 保留 90 天且**保留 trace**（`run_id + step_index + trace_id` 是把失败追回 Java 请求的唯一线索）；`RUNNING`/`WAITING_*` **任何年龄都不动**（等待中的 checkpoint 就是产品本身，回收它会把暂停的 run 变成不可恢复）。retention **不是删除**：run 行永久保留，只打 `checkpoint_compacted_at` 标记，且全部操作幂等。
- **集成测试的连接与清理语义**：无可用数据库时 **skip 而非 fail**；每个用例用随机 `run_id` 并在 teardown 删除（checkpoint/trace 级联），实测跑完后 `agent_checkpoints` 计数回到 **0**，不污染开发库。
- **环境说明（非代码问题）**：本沙箱下 `uv run` 无法写 `%LOCALAPPDATA%\uv\cache`，四条门禁以等价的 `.venv\Scripts\python.exe -m ...` 形式执行；Java Testcontainers 需要 Docker 命名管道（工作区之外），首次 `verify` 的 44 个错误全部是 `Could not find a valid Docker environment`，提权重跑即通过。
- **V002 已在开发库实际应用**（实测 `Successfully applied 1 migration to schema "commerce", now at version v002`），因此 Python 集成测试跑在真实迁移后的 schema 上，而非仅靠 Testcontainer。

### T018 验收证据

- **验证页结构纠偏（2026-09-22）**：T018 首版把 `App.tsx` 整体替换成单任务 chain check，覆盖了 `demo/t016-flow-playground` 中已经由用户实际操作过的 T016 流程与故障注入按钮。现已恢复 T016 Playground，并把 T018 控件嵌回同一个调试器；后续任务在这条既有 Flow 上增加按钮或查看能力，不再另开独立任务页面。

- **契约复验（2026-09-22，直连 8000 + 真实 PostgreSQL）**：纠偏后重新按契约复验 16 项（创建/读取/事件、403 与 409 分离、四类 401、claims 无授权效力、404 与 422、先鉴权再判状态），全部符合契约；并确认 `agent_app` 对 `commerce.*` 无权限（`permission denied for schema commerce`），Python 无法绕过 Java 直接读权威用户表。复验中发现并修掉一个**运行环境缺陷**：8000 上 15:21 启动的历史进程因缺少 `trust_env=False` 而读取系统代理，导致带合法 token 的请求全部 502；当前代码已含该修复，杀进程重启后复验通过。明细见 `docs/devlog/2026-09-22.md`。**唯一未覆盖项**：Vite `/agent` → `/api/v1/agent` rewrite（页面冒烟：步骤 08 应返回 201）。

- **Python 四条门禁全绿**：`ruff check` **All checks passed** / `ruff format --check` **39 files** / `mypy app` **Success 24 files** / `pytest -q` **234 passed, 13 skipped**（其中 T018 集成 18 个、凭据单测 21 个）。
- **Web**：`npm.cmd run build` 成功（`dist/` 产出）；`npm.cmd run lint`（oxlint）**0 warnings / 0 errors**。
- **5173 真实端到端流转测试（实测通过）** —— 这是本节的核心验收，链路为 `浏览器 → localhost:5173 (Vite dev proxy) → FastAPI:8000 → stub Java /me → PostgreSQL(agent.*)`：

  | 请求（全部经 `localhost:5173`） | 结果 |
  |---|---|
  | `GET /health` | **200** |
  | `POST /agent/runs` | **201**，返回 `runId` / `status=RUNNING` / `version=1` |
  | `GET /agent/runs/{id}`（本人 token） | **200** |
  | `GET /agent/runs/{id}`（customer-002 token） | **403** |
  | `GET /agent/runs/{id}/events` | **200**，含 `STATE_TRANSITION` checkpoint 事件 |
  | `GET /agent/runs/{id}`（无 token） | **401** |

  并直接查库确认 `agent.agent_runs` 有该行（`customer-001 / RUNNING / version=1 / created`）、`agent.agent_checkpoints` 1 条；测试后已清理，开发库回到 7 条 demo run。
- **"本地验签只做快速失败、绝不做授权依据"由类型保证**：`VerifiedCredential` 只有 `issuer` / `expires_at` / `verified_at` 三个字段，**没有 `user_id`/`role`/`subject`**，`test_verified_credential_carries_no_identity` 钉死这一点。因此"从 JWT claim 读 role 去授权"在类型层面写不出来。
- **凭据验证的四条硬要求各有可执行证据**：HS256 验签、算法固定（`alg: none` 被拒）、issuer 匹配、`exp` 必须存在（无 `exp` 的 JWT 永久有效，缺失即失败）；`iat` 刻意不要求，并有测试说明理由。
- **失败语义分三档**：缺凭据/验签失败 → **401**；权威服务明确拒绝 → **401**；**权威服务不可达 → 503**（返回 401 会告诉一个认证正确的客户端"你的 token 坏了"，既假又不可操作）。有专门测试（Java 连接失败断言 503）。
- **403 与 409 分离**：403 = "这个 run 不是你的"（鉴权，owner 进 SQL 谓词）；409 = "你的 run 现在不能推进"（状态合法性）。且**先鉴权再判状态**，否则不拥有者可用状态码差异探测他人 run。
- **端点全部需要认证由测试枚举验证**（6 个端点逐一断言 401），且认证声明在 **router 级** —— 这是弥补 FastAPI 没有 SecurityFilterChain 的补偿控制：新端点默认需要认证。
- **本轮抓到的真实缺陷（均由集成/端到端测试发现，非人工检查）**：
  1. `Depends(get_settings)` 与 app 自身 settings 不一致（`lru_cache` 与 `Settings(...)` 分叉）——同一根因造成两次故障：所有已认证请求 401、以及 run 的 `max_steps` 用了 12 而非 app 的 5（T015"创建时注入预算"静默失效）。根治为 `get_settings_from_app` 单入口。
  2. lifespan 无条件重建 `CommerceClient`，覆盖测试注入的 stub → 测试**打到了 :8080 上真实运行的 Java**，症状伪装成"验签坏了"。
  3. Vite proxy 缺 path rewrite → `/agent/runs` 全部 **404**（app 注册在 `/api/v1/agent/runs`）；该 404 看起来像"路由未注册"，只有端到端测试能发现。
  4. 测试 fixture 第一版 teardown 会删 `user_id LIKE 'customer-%'` 的所有行 —— 对共享开发库具破坏性，已改为只删自己登记的 id。
- **环境陷阱（记录以免下次误判）**：本机 Vite dev server 只监听 **IPv6 `::1`**，所以 `http://127.0.0.1:5173/` 连不上，必须用 `http://localhost:5173/`；这与 T017 的 PostgreSQL（只绑 IPv4，`localhost` 先试 `::1` 白等 5 秒）**方向恰好相反**。结论：不要记"用 127.0.0.1"或"用 localhost"的口诀，按目标服务实际监听地址决定。
- **明确未做（不夸大本节范围）**：`/events` 目前返回 JSON 数组而非 `text/event-stream` 流（契约声明 SSE，内容正确、传输留 UI 阶段）；`/input`/`/resume` 只做门禁与 resume，**不解释文本**（理解属 T030）；没有真正调用 LLM、没有查订单、没有退款（T029/T030/T026）。

### T019 验收证据

> **Post-review hardening（当前提交）**：在最初 75-test 通过后，又补了 `PAID + no shipment` 的 non-retryable 回归用例并收紧相关契约。下面的 **75 / OrderLogistics 14** 是该补丁之前的真实本机基线；新提交尚未重新本地执行 `mvnw.cmd verify`，因此这里不把总数擅自改成 76，也不把新增用例写成“已通过”。

- **Java `mvnw.cmd verify` → BUILD SUCCESS**（本机实测 2026-09-22 17:53：Tests run: **75**, Failures: 0, Errors: 0, Skipped: 0；Spotless **73 files clean / 0 needs changes**；SpotBugs **BugInstance size 0** / Error size 0；JaCoCo 分析 **50 classes**）。新增 `OrderLogisticsIntegrationTest` **14 个用例全过**，每类逐个复核：AfterSalesRule 2 / AgentRunCheckpointSchema 9 / AuditWriter 7 / ApplicationTests 1 / TraceIdFilter 15 / CoreSchemaMigration 3 / DatabaseGeneratedValues 1 / ErrorEnvelope 6 / FixtureProfileDeclaration 2 / FixtureLoader 5 / JwtSecurity 7 / OrderConcurrencyGuarantees 3 / **OrderLogistics 14** = 75。
- **交付内容（7 个生产文件 + 1 个测试文件）**：
  - `order/OrderService.java` —— ownership 的**唯一**判定入口 `requireOwnedOrder`，加上 `getOrder` / `listOwnOrders` 两个客户维度读方法；
  - `order/OrderSnapshot.java` / `order/OrderSummary.java` —— 契约对齐的 detached 读模型；
  - `logistics/LogisticsService.java` —— 物流读（先过 ownership 再读运单）；
  - `logistics/LogisticsStallCalculator.java` —— 物流派生事实的唯一计算处（签收判定 + 停滞时长）；
  - `logistics/LogisticsSnapshot.java` —— 物流读模型 + `stalledAtLeast` 阈值比较；
  - `common/time/ClockConfig.java` —— `Clock` 时间 seam。
- **越权读的 404 concealment 口径已从"实现选择"升级为"契约规则"**（2026-09-22，用户确认）：`commerce-api.openapi.yaml` 升到 `0.2.1`，在 `info.description` 写入全局 **Ownership concealment rule**；`GET /orders/{orderId}/logistics` 补上 `404`（它此前只声明 `403`/`503`，与 concealment 自相矛盾）；两个 read 端点的 `403` 明确为"已认证主体缺少角色/能力权限"→ `ACCESS_DENIED`，**绝不用于 ownership 失败**。`error-contracts.md` 新增同样规则的专章并把 taxonomy 里的 `ORDER_FORBIDDEN` **整条删除**——它描述的正是"订单属于别人"，按 concealment 必须与"不存在"不可区分，因此**没有合法的生产方**；留着一个没有合法出口的错误码，只会诱导后续实现者重新引入存在性泄露。`tool-contracts.md` 的 `get_order` / `get_logistics` 错误码同步（去掉 `ORDER_FORBIDDEN`，补 `ACCESS_DENIED` 与 `LOGISTICS_UNAVAILABLE`）。Java `ErrorCode.ORDER_FORBIDDEN` 随之删除。
- **"对外抹平"不等于"内部失明"（可执行证据）**：`OrderService` 在判定失败后额外用 `existsById` 区分两种情况，只对 **cross-owner** 写结构化安全审计（`commerce.audit_logs`，`action=ORDER_ACCESS_DENIED`，`metadata.reason=CROSS_OWNER`、`concealedAs=ORDER_NOT_FOUND`），普通 404 **不写**（否则一次 id 扫描就能刷爆审计表，把真正的越权信号淹掉）。两条失败路径都会执行 `existsById`，避免最粗粒度的查询数量差异；但 cross-owner 还会额外写一条 `REQUIRES_NEW` 安全审计，因此这里只承诺 **status / errorCode / message concealment**，**不宣称 constant-time**，也不把“无时序侧信道”写成已证明结论。
- **审计失败不得改变对外结果**：只有 cross-owner 路径会写审计，若审计异常向上传播，"审计挂了 → 500"就重新变成可探测信号，把刚抹平的区别又泄露出去。请求本来就要被拒绝，丢掉的只是可观测性而非业务动作，因此捕获后记 ERROR 日志，仍抛出统一的 `ORDER_NOT_FOUND`。
- **SpotBugs 新增 1 条最窄豁免，并且抓到自己的一个静默失效**：`OrderService` 现在注入**具体类** `AuditWriter`（此前注入的都是仓储接口），触发 `EI_EXPOSE_REP2`；该字段是 private final、仅用于调用 `writeSecurityEvent`、不经公开 API 暴露，属于 exclude 文件开头那段注释描述的可证明误报，因此按类+字段做最窄豁免。**首次加豁免后 SpotBugs 反而报了 4 条**——包括 3 条早就存在的旧豁免。原因是我在 XML 注释里写了 `--`（`do not -- that is`），而 XML 规范禁止注释内出现 `--`，导致整个 filter 文件**非良构**并被 SpotBugs **静默忽略**（不报解析错误）。修正后回到 `BugInstance size 0`。已在 exclude 文件里写下这条"改这个文件时要注意"的警告。
- **越权读刻意"对外不可区分"（服务层实现）**：不存在 vs 属于别人，统一 `ErrorCode.ORDER_NOT_FOUND`，且两条失败路径的 `getMessage()` **逐字相同**（测试直接断言消息相等）。理由：fixture 的订单 id 形如 `order-001`，可枚举；若对别人的订单回 403，攻击者就能用状态码差异枚举出哪些 orderId 真实存在（存在性预言机）。角色/能力不足走 `ACCESS_DENIED`。
- **停滞计算的四个口径各有独立用例**（都指向 fail-closed，即"少退款"方向）：
  1. **基准取更近的一方**：`max(shipments.last_event_at, MAX(logistics_events.occurred_at))`。投影列与事件表之间**没有任何数据库约束防漂移**，取较大值 = 低估停滞时长。测试构造了两个相反方向的漂移（100h/30h 与 30h/100h），结论都必须是 30h。
  2. **没有物流事实就不编造**：两个来源都空 → `lastMeaningfulEventAt`/`stalledHours` 都是 `null`，**不回落**到 `orders.shipped_at`。`null` 表示"不知道"，与"停滞 0 小时"是两件事；`stalledAtLeast(48)` 在 `null` 上返回 `false`。
  3. **向下取整**：47h59m → 47h，不达 48h 阈值；整 48h 才算达到（`>=` 取等号）。
  4. **已签收 ⇒ 不存在停滞**：`signed` 由 `signed_at != null || status = DELIVERED` 派生（两来源任一成立即算已签收，冲突时偏向"已签收"），已签收时 `stalledHours = null`——否则 US2 的退货路径会被 US1 的退款路径抢走。
- **时间戳落在未来时夹到 0，但原始事实照实暴露**：`lastMeaningfulEventAt` 仍然返回那个未来时间戳，异常看得见；只是不把它算成停滞。既不谎报，也不销毁信息。
- **"确定性计算"由类型保证，不靠约定**：`LogisticsStallCalculator` 从注入的 `Clock` 取"现在"，生产是 `Clock.systemUTC()`，测试用 `@TestConfiguration` + `@Primary` 覆盖成 `Clock.fixed`。因此测试能对停滞时长做**精确**断言（120h / 30h / 47h / 48h），而不是"应该大于 48 吧"这种随时间腐烂的模糊断言。
- **订单列表的 ownership 是集合性质**：测试断言 `listOwnOrders(OWNER)` 的 id 列表**恰好等于** `["t019-order-mine"]`，而不是"不含某人"这种否定式写法。
- **读模型而不是实体**：`open-in-view: false` + `Order.items` 是 LAZY ⇒ 一旦把实体交给 controller，`getItems()` 就会 `LazyInitializationException`。这是 Service 必须返回 detached snapshot 的真实原因。
- **no-shipment 按订单状态区分，不再一律报 retryable 503**：`PAID + no shipment` 表示尚未进入物流生命周期，返回 non-retryable `INVALID_ORDER_STATE`；`SHIPPED + no shipment` 才表示按当前业务状态本应存在权威物流记录却缺失，返回 retryable `LOGISTICS_UNAVAILABLE`。两种情况都不返回空快照让 Agent 猜。
- **本 T 发现的契约不一致已闭环**（原状态：`GET /orders/{orderId}` 同时声明 `403`+`404`，而 `GET /orders/{orderId}/logistics` 只声明 `403`/`503`、没有 `404`）。用户 2026-09-22 拍板采用 **404 concealment 口径统一契约**，处置见上面两条。教训：契约在实现前写成，出现自相矛盾时实现者应当**把它作为发现报出来**，而不是静默挑一个继续往下写。
- **刻意保留的一处不等价（有理由，不是遗漏）**：Agent 侧 `POST/GET /runs/*` 对 cross-owner run 仍返回 **403 `RUN_FORBIDDEN`**（T018 已验收的口径），与订单侧 404 concealment **故意不同**。判据是**标识符的可猜性**而不是端点形状：`run_id` 是随机 UUIDv4，确认"这个 id 存在"给不了攻击者可枚举的东西；`orderId` 形如 `order-001`，短且可猜。concealment 是有成本的取舍（可诊断性换抗枚举），不是教条。`runs.py` 的过时注释（引用已删除的 `ORDER_FORBIDDEN`）已改写为这条理由；Python 四条门禁复跑全绿（`ruff check` All checks passed / `ruff format --check` **39 files** / `mypy app` **Success 24 files** / `pytest -q` **234 passed, 13 skipped**）。
- **本 T 的层位置与未覆盖项（不夸大范围）**：T019 为了让集成测试真正 red→green，已经提前落地了 T023/T024 的 **service read-side**（`OrderService`、`LogisticsService` 与 stall calculator）；T023/T024 仍未完成，因为 **Controller / HTTP assembly / endpoint role enforcement** 还没有实现。T023/T024 后续必须复用这些 service，而不是重写一套。T019 没有 `Idempotency-Key`、没有任何写操作、没有退款；eligibility 属 T025，退款属 T026/T027。
- **已知 tradeoff（写明白而不是藏起来）**：`OrderService.requireOwnedOrder` 返回 `Order` 实体，因此 `Order` 跨包对 `logistics` 可见。V1 接受，因为调用方只读；一旦有调用方基于这个返回值写订单，写路径必须自己重新校验"当下仍然合法"，不能复用"读的时候合法"这个结论。
- **环境说明（非代码问题）**：Testcontainers 需要工作区之外的 Docker 命名管道，受限沙箱下**首次** `mvnw verify` 以 `Previous attempts to find a Docker environment failed` 失败（56 errors，**包含 T013/T014/T016–T018 的既有测试**，因此可判定为环境而非代码）；提权重跑同一条命令即 BUILD SUCCESS。

## 维护规则
- 每完成一个 Gate 更新本文件；不要每天机械改百分比。
- 每次开发只关注当前 Phase，不主动扩展下一阶段。
- `tasks.md` 是详细执行清单，本文件只做导航，不复制全部 Task 内容。
- 实际代码行为与本文不一致时，以 Constitution / Spec / Plan / Tasks 为准，并及时更新本文件。
