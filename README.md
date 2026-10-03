# CommerceAgent

企业电商售后执行与异常处置 Agent。

> 当前状态：**Phase 3 — US1 MVP**。**T019–T031 已完成并验收**；当前是 **T032（LangGraph 装配）进行中、未验收** —— 节点与路由已实现 7/10，终态节点、持久化接缝与生产接线尚未完成。
>
> 仓库中的性能、安全、时延、成本和成功率等指标，在没有实际 Eval 运行产物之前都只视为目标，不视为已达成结果。

## 项目要解决什么问题

CommerceAgent 不是 FAQ ChatBot，也不是固定的“识别退款意图 → 调退款接口”工作流。

它面向电商售后场景，让 Agent 根据订单、物流、业务规则和审批等证据动态决定下一步动作，并通过受保护的业务 Tool 执行退款、退货、澄清、审批或安全停止。

核心链路：

```text
User
  ↓
Python Agent
  ↓
Allowlisted Business Tools
  ↓
Java Business Backend
  ↓
PostgreSQL
  ↓
Verified Result + Structured Trace
```

## 核心设计原则

- **LLM 不负责资金类最终授权**：订单归属、退款/退货资格、金额、审批和状态迁移由 Java 后端确定性校验。
- **写操作必须幂等且可验证**：超时结果未知时先查询权威状态，禁止盲目重复写入。
- **Agent 行为必须依赖证据**：同一句退款类请求在不同业务状态下，应能够走向退款、退货、澄清或等待审批等不同路径。
- **政策检索不等于业务授权**：非结构化政策只能用于解释和引用，不能覆盖结构化业务规则。
- **Trace 不保存隐藏思维链**：只记录状态迁移、Tool、参数摘要、结果、错误、重试、审批和写后验证。

## 当前实现进度

项目已经完成 Setup + Foundation，并进入 **Phase 3 — US1 物流异常退款闭环**。当前已完成的主链能力包括：

- **T018**：FastAPI Agent Run 骨架、认证 / ownership、Checkpoint / Structured Trace 持久化，以及 5173 Flow Playground 基线；
- **T019–T020**：ownership-scoped 订单 / 物流读取、权威物流停滞计算、deterministic EligibilityDecision；
- **T021–T022**：受保护退款写入、数据库幂等约束、订单行锁、unknown-write recovery、write-ahead intent；
- **T023–T025**：订单、物流、Eligibility 的真实 HTTP API 与 5173 live 验证；
- **T026**：`commerce.refund_requests` migration + Entity / Repository 已随 T021 交付；
- **T027**：RefundService 的 ownership / current-state / eligibility / amount 写前重校验、幂等、行锁、审计和状态读面已落地；真正的 approval binding 留到 US4/T049；
- **T028**：已暴露 `POST /api/v1/refunds` 与 `GET /api/v1/orders/{orderId}/after-sales`，后者支持可选 `idempotencyKey` 精确过滤，为 unknown-write recovery 提供权威读后验证。HTTP 集成测试 **8/8**，Maven **BUILD SUCCESS**。
- **T029**：已新增 `app/tools/`，实现六个 US1 typed tools、统一 `ToolEnvelope`、显式 allowlist、risk metadata 与 name→bound implementation 映射；`create_refund_request` 为唯一 high-write Tool，写超时归一为 `WRITE_TIMEOUT_UNKNOWN` 且禁止盲重试。另新增 dev/test-only `/api/v1/agent/dev/tools/execute` 与 `T029 · LIVE TOOL` Flow Playground，用于观察安全只读/判定 Tool 的真实链路（不暴露 high-write Tool）。5173 已实测 `get_order`、`get_logistics`、`check_after_sales_eligibility`、`get_after_sales_status`，并验证 missing key → `refunds=[]`、cross-owner 与 missing order → 同样 `ORDER_NOT_FOUND`。最终 Python `ruff check` / `ruff format --check` / `mypy` 全绿，`pytest` **285 passed, 6 skipped, 6 warnings**；Web `npm.cmd run build` / `npm.cmd run lint` 全绿。
- **T030**：真实 OpenAI-compatible 模型只做请求理解与受限 evidence capability 建议；`mentionedOrderId` 仅是线索，必须经 Java ownership-confirmed `get_order` 才能成为 `resolved_order_id`；确定性 guard 复核 registry risk、当前状态与重复证据；`stalledHours` / eligibility / 金额始终由 Java 计算。另加 dev/test-only `/api/v1/agent/dev/t030/run` 与 `T030 · LIVE AGENT`。
- **T031**：Agent 侧写后权威校验与持久化接缝 —— `verify_business_state.py` 按**同一** idempotency key 读 Java 权威状态（读失败 → `UNKNOWN`；权威返回空 → `VERIFIED_FAILURE`；同 key 多条或 id 不符 → `UNKNOWN`，**自己不重试**）；`execute_write.py` 改写为经 T029 typed tools 执行与恢复；`PostgresRunStore.checkpoint_state()` 新增 CAS 全量状态快照；`app/api/dev_t031.py` 提供 dev-only live harness。**收口时修掉 9 个远端提交带进来的 lint/format 债**，四条 Python 门禁全绿（`pytest` **344 passed, 6 skipped**）。

> **T032 进行中（未验收）**：`app/agent/` 下已新增 `graph.py`（`GraphState` + 显式条件边目标表 + 装配校验 + `compile(checkpointer=None)`）、`routing.py`（路由表 / 预算 / `SafeStopReason` / `HandoffReason` / `TerminalDecision`）、`nodes.py`（**10 / 10 节点**，含终态 `finalize` / `safe_stop` / `waiting_user`）、`runtime.py`（`RunSession` 的三个写 seam + `drive_graph`：版本跟踪、边界写延迟一步、失败收尸）、`wiring.py`（10 节点 + 9 依赖的唯一组装点），`state.py` 增 `advance()` 作为唯一校验变更入口；`runs.py` 的 `/input` 与 `/resume` **现在真的组装图并驱动 run**。**未完成**：5173 live 验收、`agent.tool_executions` 工具 trace 接线（障碍见设计文档 §10）、`/input` 与 `/resume` 的 HTTP happy-path 用例。**三个入口都会驱动 run**：`POST /runs` 是第一次 invocation 的**唯一入口**（契约没有 execute 端点，`/input` 与 `/resume` 又都要求 run 处于 `WAITING_*`），驱动做成可注入的 `RunDriver` 接缝，`check` 在写任何东西之前拒绝——避免留下一个没人能推进的 `RUNNING` run。**真库 E2E 已在真实 PostgreSQL 上跑通**（`tests/integration/` 共 65 passed，含新接缝 6 个用例）。**所以"节点与接线齐备"不等于"live 已验证"**，T032 仍**不得勾选**。设计见 [`specs/002-commerce-after-sales-agent/t032-runtime-design.md`](specs/002-commerce-after-sales-agent/t032-runtime-design.md)。

当前下一步：

- **T032 剩余三件**：① 5173 live 验收；② 工具 trace 接线（先定"缺 trace id 怎么记、risk 从哪取"）；③ `/input` 与 `/resume` 的 HTTP 用例；
- 之后按 `tasks.md` 进入 **T033**（Run 序列化只返回已验证事实）与 **T034**（最小 Customer Console）。

> 说明：Flow Playground 已有 `T028 · LIVE REFUND` 的 create + verify 控件；最近一次手工 5173 尝试命中了未重启的旧 8080 Java 进程，因此这里不把该次尝试写成成功验收证据。

> `pgvector/pgvector` 镜像已作为未来能力基线使用，但 **T005 不启用 `vector` extension，也不创建向量表**；是否启用向量检索由 US6 / T065 决定。

## 项目总架构入口

如果你想从一张总图理解整个项目，包括 Web、React、TypeScript、Vite、npm、Python、FastAPI、LangGraph、Java、Spring Boot、PostgreSQL、Docker、Eval、T001–T083 的关系和完整请求链路，先看：

- [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)：**CommerceAgent 全项目架构与学习地图**
- [`PROJECT_PROGRESS.md`](PROJECT_PROGRESS.md)：当前做到哪一阶段、下一步做什么

## 仓库结构

```text
commerce-backend/   # Java 业务后端
agent-service/      # Python Agent Service
web/                # React + TypeScript Web
infra/              # PostgreSQL / Docker Compose
specs/              # Spec / Plan / Research / Tasks / Contracts
.specify/           # Spec Kit 项目配置
.agents/skills/     # Spec Kit 初始化生成的项目内 speckit-* 工具
```

### `specs/001-agent-career-project`

回答：**为什么最终选择 CommerceAgent？**

包含招聘市场调研、能力地图、项目候选、Fatal Gate、评分、Red Team 和最终选题依据。

### `specs/002-commerce-after-sales-agent`

回答：**CommerceAgent 具体怎么做？**

主要入口：

- [`spec.md`](specs/002-commerce-after-sales-agent/spec.md)：项目 PRO / 功能规格
- [`plan.md`](specs/002-commerce-after-sales-agent/plan.md)：实施计划与架构
- [`research.md`](specs/002-commerce-after-sales-agent/research.md)：技术决策
- [`data-model.md`](specs/002-commerce-after-sales-agent/data-model.md)：数据模型与状态规则
- [`quickstart.md`](specs/002-commerce-after-sales-agent/quickstart.md)：验收路径与 Agent Value Gate
- [`contracts/`](specs/002-commerce-after-sales-agent/contracts/)：API / Tool / Error 契约
- [`tasks.md`](specs/002-commerce-after-sales-agent/tasks.md)：实现任务清单

## 计划技术栈

- Java 21 + Spring Boot 4.1.1
- Python 3.13 + FastAPI + LangGraph
- React + TypeScript + Vite
- PostgreSQL
- Docker Compose
- JUnit / Testcontainers / pytest

## 第一实现目标

优先打通 US1 纵向切片：

```text
用户提出物流异常退款请求
→ Agent 理解诉求并定位订单
→ 查询订单与物流
→ Java 进行 deterministic eligibility
→ 创建幂等 RefundRequest
→ 查询并验证最终业务状态
→ 返回 verified result + structured trace
```

在这个闭环真实跑通前，不扩展 MCP、Multi-Agent、Kafka、Kubernetes 或装饰性 Dashboard。

## 当前非声明项

本项目当前**不声称**：

- 已接入真实淘宝 / 京东 / ERP / 支付系统；
- 已达到任何生产级成功率、延迟或安全指标；
- 已完成 60/74 条 Eval；
- 已完成 RAG、HITL、全部 User Story 或生产部署。

这些内容只有在实际实现并产生可复现证据后，才会更新到 README。
