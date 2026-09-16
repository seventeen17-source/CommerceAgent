# CommerceAgent

企业电商售后执行与异常处置 Agent。

> 当前状态：**设计阶段已完成，正式实现即将开始。**
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

## 仓库结构

```text
.specify/
  memory/constitution.md

specs/
  001-agent-career-project/
  002-commerce-after-sales-agent/
```

### `001-agent-career-project`

回答：**为什么最终选择 CommerceAgent？**

包含招聘市场调研、能力地图、项目候选、Fatal Gate、评分、Red Team 和最终选题依据。

### `002-commerce-after-sales-agent`

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

- Java 21 + Spring Boot 3.5.x
- Python 3.13 + FastAPI + LangGraph
- React + TypeScript + Vite
- PostgreSQL
- Docker Compose
- JUnit / Testcontainers / pytest

当前尚未提交正式实现代码；后续基础工程将使用 Spring Initializr、`uv init` 和 Vite 官方脚手架生成。

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
