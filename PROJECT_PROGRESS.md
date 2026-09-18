# CommerceAgent Project Progress

> 这是项目的唯一阶段导航文件。每次开始开发先看这里，再去 `tasks.md` 找当前阶段任务。

## 当前状态

- **当前 Phase**：Phase 2 — Foundational
- **当前 Tasks**：T012（实现完成，待本地验收）（实现完成，待本地 `mvnw verify` 验收）
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
- **当前优先任务**：T012 — 统一 error envelope
- **下一 Gate**：完成 T010 后，进入 T011–T014 的 Security / Error / Audit / Fixture 基础能力
- **当前 Blocker**：无
- **环境事实（重要）**：
  - 本机 PowerShell 执行策略为默认 `Restricted`，`npm` 会命中被拦的 `npm.ps1` → **前端命令一律用 `npm.cmd` / `npx.cmd`**
  - 本机 `core.autocrlf=true`；`infra/` 下的脚本与 `.env*` 已由根 `.gitattributes` 钉为 LF（否则容器内执行会 `bad interpreter`）
  - 数据库容器 `commerceagent-postgres`，宿主端口 **5432**，并仅绑定 `127.0.0.1:5432`；Adminer 仅绑定 `127.0.0.1:8081`
  - 原 `opspilot-db` 已废弃并移除，其数据卷 `opspilot_agent_pgdata` 保留未删
  - 启动数据库：`docker compose -f infra/docker-compose.yml up -d`（首次可 `cp .env.example .env` 覆盖默认值）
  - Java 侧两条命令：`mvnw.cmd spotless:apply` 修复格式；`mvnw.cmd verify` 跑 compile + test + spotless check + SpotBugs + JaCoCo
  - Testcontainers PostgreSQL 已固定为 `postgres:18`，避免 `latest` 漂移破坏可复现性
  - Python 侧三条命令：`uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy app`
- **未决项**：
  - `.specify/feature.json` 本地仍指向 `specs/001-agent-career-project`，后续应切换为 `specs/002-commerce-after-sales-agent`
- **Skill 规则**：`main` / 功能分支保留 Spec Kit 初始化生成的 `.agents/skills/speckit-*`；`project-coding-tutor` 等自定义 Skill 源码统一维护在 `skills_` 分支或安装为本地/全局 Skill
- **明确延期**：US6 Policy/RAG、独立 Eval Dashboard、MCP、Multi-Agent、Kafka、Kubernetes、花哨 UI

## 阶段总览

| Phase | 目标 | Tasks | Gate | 状态 |
|---|---|---|---|---|
| 0 | 设计冻结 | — | 002 Spec / Plan / Tasks / Contracts 已对齐 | ✅ Complete |
| 1 | 官方项目脚手架 | T001–T007 | Java / Python / Web 可启动，PostgreSQL 基础配置就绪 | ✅ Complete（T001–T007 ✅） |
| 2 | Foundation | T008–T018 | AgentRun / Auth / DB boundary / Trace 基础能力可用 | 👉 Current（T008–T011 ✅，当前 T012） |
| 3 | US1 MVP | T019–T035 | 物流异常 → eligibility → refund → verification 真实 E2E 跑通 | ⬜ |
| 4 | Agent Value | T036–T048 | 同类请求可因证据走退货 / 澄清等不同路径 | ⬜ |
| 5 | HITL | T049–T056 | 高风险动作等待权威审批并可恢复执行 | ⬜ |
| 6 | 安全降级 | T057–T063 | 依赖失败 / 规则冲突时 Safe Stop 或转人工 | ⬜ |
| 7 | Policy / RAG | T064–T070 | 政策证据可检索引用，但不掌握资金授权 | ⬜ Optional/P2 |
| 8 | Eval & Portfolio | T071–T083 | Eval、CI、Docker、README、Demo、真实指标完成 | ⬜ |

## Phase 1 — 完成记录

1. ✅ 拉取最新 `main` 并确认工作区干净
2. ⬜ 本地 `.specify/feature.json` 指向 `specs/002-commerce-after-sales-agent`（当前仍为 001）
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
5. ⬜ T012：统一 Error Envelope
6. ⬜ T013：结构化 Audit Writer
7. ⬜ T014：dev/eval fixture loader
8. ⬜ T015–T018：Agent State / Commerce Client / Run+Trace / FastAPI security skeleton

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

## 维护规则

- 每完成一个 Gate 更新本文件；不要每天机械改百分比。
- 每次开发只关注当前 Phase，不主动扩展下一阶段。
- `tasks.md` 是详细执行清单，本文件只做导航，不复制全部 Task 内容。
- 实际代码行为与本文不一致时，以 Constitution / Spec / Plan / Tasks 为准，并及时更新本文件。
