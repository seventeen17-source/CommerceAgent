# CommerceAgent 中文简历项目模板

> 注意：以下所有数字均为占位符。只有真实实现并完成可复现实验后，才允许替换为 measured/approved 结果。

## 项目名称

**CommerceAgent — 企业电商售后执行与异常处置 Agent**

## 一句话描述

面向电商售后场景构建可执行 Agent，将自然语言投诉转化为跨订单、物流、售后规则和退款/退货系统的多步业务处置流程；Agent 负责动态取证与工具编排，Java 后端负责权限、退款资格、金额、幂等和状态安全。

## 简历要点模板

- 设计并实现企业级电商售后执行 Agent，覆盖订单识别、物流异常分析、售后政策检索、退款/退货资格校验、人工审批与业务写入，避免将系统退化为 FAQ ChatBot。
- 将不确定 Agent 决策与确定性业务规则分离：Python Agent 负责意图理解、证据收集和 Tool Calling，Java/Spring Boot 负责订单权限、退款资格、金额计算、状态机、事务、幂等与审计。
- 针对退款 API 超时、重复调用、Prompt Injection、越权订单访问和高风险退款设计安全机制，通过 idempotency key、Server-side Policy、Human-in-the-loop 和写后状态验证保证业务安全。
- 构建约 **[待实测样本数]** 条版本化离线评估集，覆盖正常退款、退货、物流异常、工具选择、参数、超时、权限、注入与审批；对比 Baseline / V1 / Optimized 的任务成功率、工具准确率、安全率、延迟和 Token 成本。
- 建立 Agent Run 全链路 Trace，记录状态流转、Tool 参数/结果、检索引用、重试、审批和最终业务状态，使失败 case 可复现、可定位。

## 后续可填写的真实成果

只能在实际评估后填写，例如：
- 任务成功率：[待实测]
- Tool Selection Accuracy：[待实测]
- Unsafe Action Rate：[待实测]
- Duplicate Write Rate：[待实测]
- p50 / p95 latency：[待实测]
- Token cost：[待实测]

禁止在实现前写“提升 X%”“成功率达到 X%”等成果数字。

## 面试关键词

Agent State Graph / Tool Calling / Function Calling / Java Spring Boot / Python / FastAPI / RAG / Policy Retrieval / Human-in-the-loop / Idempotency / Prompt Injection / Authorization / Offline Eval / Observability / Trace / PostgreSQL / Docker Compose / MCP（可选扩展）
