# CommerceAgent

企业电商售后执行与异常处置 Agent。

> 当前状态：**Phase 3 — US1 MVP**。T029（Typed Tools）已完成并验收，当前进入 T030 Agent 证据收集与受限 capability 决策。
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

当前下一步：

- **T030**：实现 `understand_request`、单候选订单解析、`decide_next_evidence`、read-tool execution、evidence validation、`check_eligibility`；
- **T031–T032**：补独立 verify node，并把安全写入恢复与 LangGraph 主链正式接通。

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
