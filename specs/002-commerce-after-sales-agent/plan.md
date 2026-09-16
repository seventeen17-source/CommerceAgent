# 实施计划：CommerceAgent 企业电商售后执行与异常处置 Agent

**Feature**: `002-commerce-after-sales-agent`  
**Date**: 2026-09-15  
**Spec**: `specs/002-commerce-after-sales-agent/spec.md`

## 总体方案

构建一个边界明确的电商售后执行 Agent。系统需要处理含糊的客户意图，跨订单、物流和政策系统收集证据，根据当前证据动态选择下一项安全业务能力，并且只有在确定性业务授权允许时，才执行退款、退货或转人工等动作。

实现由以下部分组成：

- React Web UI；
- Python Agent Service，使用显式状态图；
- Java 模块化单体业务后端；
- PostgreSQL；
- 仅用于政策解释的 RAG；
- 结构化 Trace；
- 版本化离线 Eval。

---

## 技术上下文

**语言/版本**：Java 21 LTS；Python 3.13；TypeScript 5.x

**主要依赖**：Spring Boot 3.5.x、Spring Security、Spring Data JPA、Flyway、FastAPI、LangGraph Graph API、Pydantic、httpx、React、PostgreSQL、pgvector

**存储**：一个 PostgreSQL 实例，逻辑上区分：

- `commerce`：Java 业务权威；
- `agent`：Python Agent runtime / trace；
- `policy`：Python policy retrieval；
- `eval`：可选 Eval metadata。

V1 采用可复现的本地启动方式，数据库 schema ownership 必须明确。

**测试**：JUnit 5 + Spring Boot Test + Testcontainers；pytest + pytest-asyncio；contract tests；Playwright 为 Should 级别

**目标平台**：Linux Container / 本地 Docker Compose

**项目类型**：Web 应用 + Agent 应用 + Java 业务后端

**性能目标**：正确性与安全优先。先实测，再报告 p50/p95 时延、Tool Call 数、Token 使用等，不预设虚假 SLO。

**约束**：

- 6–8 周个人项目；
- 使用 synthetic/local 但 contract-realistic 的电商系统；
- Agent 不得直接访问权威 commerce 表；
- 所有状态写入必须在后端完成授权和确定性 eligibility；
- 不扩展到通用全渠道客服或大范围售前能力。

**规模目标**：一个售后领域、6–10 个 Agent Tool、轻量 Web、至少 60 个 Eval Case，目标约 74 个。

---

## Constitution Check

项目宪法为 `.specify/memory/constitution.md` v1.0.0。

当前方案满足以下不可妥协原则：

- **确定性业务权威 — PASS**：ownership、auth、eligibility、amount、legal state transition、approval validation、idempotency、transactional write 均由 Java 后端负责。
- **安全、幂等、可验证写入 — PASS**：退款/退货在写入前重校验当前状态；未知超时必须先查状态再决定是否重试。
- **基于证据改变行为 — PASS**：显式 graph state + conditional routing + Agent Value Gate 强制证明不同证据会产生不同路径。
- **不可信输入/检索/模型输出 — PASS**：Tool allowlist 固定；政策文本只能解释；不存在任意 URL/SQL/service execution。
- **可复现 Test/Eval/Trace — PASS**：计划包含 story-specific test、resettable fixture、versioned dataset、structured trace 以及可比较的 Baseline/V1。
- **有限架构/范围 — PASS**：一个 Java 单体、一个 Python Agent Service、一个轻量 Web、一个 PostgreSQL；核心不使用 Kafka/K8s/Multi-Agent/独立向量数据库。

后续如果设计违反 Constitution，必须先修设计或正式修改 Constitution，不能直接绕过。

---

## 项目结构

### 文档

```text
specs/002-commerce-after-sales-agent/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── commerce-api.openapi.yaml
│   ├── agent-api.openapi.yaml
│   ├── tool-contracts.md
│   ├── error-contracts.md
│   └── eval-internal-api.md
└── tasks.md
```

### 代码目标结构

```text
commerce-backend/
├── pom.xml
└── src/
    ├── main/java/.../commerceagent/
    │   ├── security/
    │   ├── order/
    │   ├── logistics/
    │   ├── eligibility/
    │   ├── refund/
    │   ├── returns/
    │   ├── approval/
    │   ├── ticket/
    │   ├── audit/
    │   └── fixture/
    └── test/

agent-service/
├── pyproject.toml
└── app/
    ├── api/
    ├── agent/
    │   ├── graph.py
    │   ├── state.py
    │   ├── routing.py
    │   └── nodes/
    ├── tools/
    ├── clients/
    ├── rag/
    ├── trace/
    └── config/

web/
└── src/
    ├── features/chat/
    ├── features/approvals/
    ├── features/runs/
    ├── features/eval/
    └── api/

eval/
├── datasets/
├── runner/
├── scorers/
├── baselines/
└── reports/

knowledge/
└── policies/

infra/
└── docker-compose.yml
```

**结构决策**：Java 负责领域规则、事务和业务状态；Python 负责 Agent state/orchestration、Tool adapter、RAG 和 Eval；React 仅作为演示和轻量运营界面。PostgreSQL 是唯一核心 datastore。服务之间优先 HTTP/JSON；MCP 仅作为后续 Should 级适配器。

---

## 数据库边界

使用一个 PostgreSQL 是为了降低本地复现成本，不代表服务边界消失。

- Java 应用代码拥有并访问权威 `commerce` 数据。
- Python 应用代码拥有 `agent` runtime/trace 和 `policy` retrieval 数据。
- Python **不得**直接查询/写入 `commerce` 表，只能经过类型化 Java API。
- Eval fixture reset 由 Java 提供内部接口，仅在 test/eval profile 下启用，因为权威 commerce state 属于 Java。

具体 migration/checkpoint ownership 在实现前必须保持与 `research.md` 一致。

---

## 架构决策

### Java 模块化单体

不拆微服务。售后场景更需要可靠的业务规则、事务、幂等和状态机，而不是分布式系统仪式感。领域模块保持清晰，但部署为一个应用。

### Java + Python 双运行时

保留双运行时的前提是两侧都有实质职责：

- Java：业务不变量和安全写入；
- Python：显式 Agent Graph、Tool orchestration、RAG、Eval。

如果任何一侧退化成纯透传代理，应重新评估是否需要继续拆分。

### LangGraph Graph API

选择显式 Graph/State API，是因为系统确实需要条件边、循环、checkpoint、interrupt、Human-in-the-loop resume 和有限重试。

实现必须公开自己的 State Schema、Node 和 Routing Decision，不能把核心流程藏在黑盒 generic agent factory 里。

### PostgreSQL + pgvector

结构化 commerce truth 保留在关系数据库中。若实现 policy vector retrieval，可使用 pgvector，避免额外独立向量数据库。

### HTTP First，MCP Later

核心 Tool Contract 使用类型化 HTTP/JSON。只有当 Tool semantics、auth、retry/idempotency 已稳定，才考虑 MCP 适配器。

### Eval CLI/File First

核心 Eval Runner 不是线上服务。它通过 eval-only Java Reset Contract 重置业务状态，运行 Agent，计算 scorer，并把机器可读结果写入 `eval/reports/`。

独立 Eval HTTP API 不属于核心要求。

---

## Phase 0 — Research 输出

`research.md` 固化：

- Java/Spring/Python 基础版本；
- Agent orchestration 方案；
- Storage/RAG 方案；
- 服务通信；
- Auth；
- Checkpoint；
- Observability；
- Eval；
- Deployment boundary；
- 明确拒绝的技术。

## Phase 1 — Design 输出

- `data-model.md`：业务、Agent Trace、Policy、Eval 实体与状态规则。
- `contracts/commerce-api.openapi.yaml`：Java Business API。
- `contracts/agent-api.openapi.yaml`：Web → Agent API、run ownership、clarification/resume。
- `contracts/tool-contracts.md`：Tool、风险、重试、授权规则。
- `contracts/error-contracts.md`：稳定 error code 与 Agent Handling。
- `contracts/eval-internal-api.md`：Eval fixture reset 契约。
- `quickstart.md`：Agent Value Gate、幂等恢复、安全与 Trace 验收。

---

## Post-Design Constitution Re-check

以下条件全部满足才允许继续实现：

1. Agent 不能绕过 ownership / eligibility / approval；
2. retry/timeout 不能产生重复退款/退货；
3. Agent state 与 Business state 分离；
4. policy retrieval 不能成为资金授权来源；
5. Agent API 强制 auth + run ownership；
6. 审批引用权威 `approvalRequestId`，不能使用模型生成审批状态；
7. Quickstart 能证明 evidence-dependent branching；
8. 项目仍然聚焦售后执行。

---

## Complexity Tracking

当前不接受任何 Constitution 例外。

Microservices、Multi-Agent、Kafka、Kubernetes、Redis-as-core、独立向量数据库、完整 Admin/RBAC 产品、真实支付网关和大范围 commerce feature 继续保持 Reject，除非未来有明确测量证据要求引入。
