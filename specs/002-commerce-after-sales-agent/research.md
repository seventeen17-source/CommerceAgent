# CommerceAgent 技术研究与决策记录

本文用于固化 `002-commerce-after-sales-agent` 的实现规划决策。目标不是堆技术名词，而是明确每一项技术为什么存在、解决什么问题，以及什么情况下应该删掉。

## 决策 1 — Java 21 + Spring Boot 3.5.x 负责业务后端

**决定**：使用 Java 21 LTS + Spring Boot 3.5.x。

**原因**：项目需要真实的确定性业务逻辑、事务、权限、幂等和审计。Java 也是用户当前更熟悉的语言，可以承担业务权威层。

**未选方案**：
- Spring Boot 4.x：核心收益有限，却增加版本兼容波动。
- Python-only backend：会削弱事务型后端能力的展示，也浪费现有 Java 优势。

## 决策 2 — Python 3.13 + FastAPI 负责 Agent Orchestration

**决定**：使用 Python 3.13 + FastAPI。

**原因**：Python 的 Agent/Eval 生态更成熟，也能补用户在 Python/Agent 工程上的短板。FastAPI 提供足够清晰的类型化 API，不需要引入更重的 Web Framework。

**未选方案**：
- Java-only Agent：可行，但减少接触当前主流 Python Agent 生态的机会。
- Flask/Django：对本项目没有明显优势。

## 决策 3 — 使用显式 LangGraph Graph API

**决定**：使用 LangGraph 显式 Graph/State，而不是黑盒 generic agent constructor。

**原因**：项目需要条件分支、循环、clarification interrupt、Human-in-the-loop pause/resume、checkpoint 和有限恢复。这些本质上是状态与工作流问题。

Graph 必须由项目自己掌控：State Schema、Node、Edge、Stop Rule 和 Tool Policy 都要显式出现在代码中。

**未选方案**：
- 开放式 ReAct Loop：难以限制步骤、难恢复、难做确定性 Eval。
- 完全手写 while-loop 状态机：可行，但会重复实现 checkpoint/HITL runtime。
- Multi-Agent：当前业务没有需要多个自主 Agent 分工的证据。

## 决策 4 — Java 使用模块化单体

**决定**：一个 Java 应用，内部保持明确领域模块。

**原因**：Order、Logistics、Eligibility、Refund、Return、Approval、Audit 共享业务状态。拆成多个微服务只会引入网络失败、服务发现和分布式事务等额外复杂度。

**未选方案**：
- 一域一微服务：对当前规模属于 architecture theater。
- 一个完全无边界的大 package：虽然简单，但会削弱测试和面试中的领域边界表达。

## 决策 5 — PostgreSQL 作为唯一核心 datastore

**决定**：业务状态、Agent trace/checkpoint metadata、审计记录以及政策检索数据都使用 PostgreSQL；若启用向量检索，使用 pgvector。

**原因**：关系数据库适合事务型 commerce state；小规模政策语料没有必要再引入独立向量数据库。

**未选方案**：
- Qdrant/Milvus/Elasticsearch：V1 没有规模需求。
- Redis 作为必选状态存储：没有测量证据前不引入。

## 决策 6 — RAG 只用于非结构化政策/SOP

**决定**：政策/SOP 可以检索，订单、物流、金额、eligibility、approval 和 after-sales status 必须走结构化 API。

**原因**：业务真相必须确定、可审计、可版本化；向量检索只适合解释性文本。

**Fallback**：如果政策语料太小，允许用“版本化政策直查”替代向量检索，不影响业务权威边界。

## 决策 7 — HTTP/JSON First，MCP Later

**决定**：Agent Tool 先调用类型化 Java HTTP API，MCP 延后。

**原因**：面试价值来自 Tool Schema、Auth、Retry、Idempotency 和安全写入，而不是“用了 MCP”这个标签。

## 决策 8 — 使用本地 JWT Fixture，不做完整身份产品

**决定**：提供最小 JWT 与预置用户/角色。

**原因**：必须展示跨用户保护，但注册、找回密码、社交登录、账号后台都不属于项目核心。

**未选方案**：
- 只用 `X-User-Id`：过于玩具化。
- 完整 OAuth/OIDC：非核心范围。

## 决策 9 — Agent checkpoint / resume 必须持久化

**决定**：持久化足够的 Agent 执行状态，以支持 `WAITING_USER`、`WAITING_APPROVAL`、clarification/HITL resume 和 run reconstruction。

**原因**：这些状态不能依赖某个 Python 进程永远存活。

**说明**：具体 checkpointer 的 schema/migration ownership 在真正初始化 LangGraph Postgres Checkpointer 前必须验证库的实际行为；第三方框架内部 checkpoint 表不得为了“统一 Flyway”而盲目复制其私有 DDL。

## 决策 10 — 核心 Trace 自己保存

**决定**：核心 AgentRun / ToolExecution Trace 存在项目自己的存储中；OpenTelemetry、LangSmith、Langfuse 等只作为可选增强。

**原因**：任何人 clone 仓库后都应该能够复盘失败 run，不依赖付费 SaaS。

Trace 记录状态迁移、Tool、参数摘要、错误、重试、审批、写入和验证，不记录隐藏 chain-of-thought。

## 决策 11 — Eval Case 放 Git，业务 Oracle 优先确定性

**决定**：Eval Case 使用版本化 YAML/JSON；Java fixture 可重置；业务状态、Tool、参数、禁止动作和重复写入优先使用确定性 scorer。

**原因**：这些指标不需要 LLM-as-judge。

**补充**：涉及模型 routing 的代表性 case，在最终报告阶段需要固定 model configuration（例如 `model_name`、`temperature`、prompt version、dataset version、git commit）；如果同一输入存在明显模型波动，则对代表性 routing case 进行重复运行并报告稳定性，而不是把一次偶然运行包装成稳定指标。

## 决策 12 — Docker Compose 作为本地部署方式

**决定**：PostgreSQL、Java backend、Python Agent Service 和 Web 使用 Docker Compose 组合运行。

**原因**：目标是可复现，不是展示集群运维。

Kubernetes 不进入核心范围。

## 决策 13 — 前端保持薄层

**决定**：Web 仅承担演示与必要操作界面。Customer Console 和 Approval Center 优先；Run Trace / Eval 展示可以后置或以内嵌/静态报告形式提供。

**原因**：前端不是本项目的核心招聘信号，不能挤占 Agent、安全写入与 Eval 的时间。

## 决策 14 — `decide_next_evidence` 使用“模型理解 + 确定性约束”的混合机制

**决定**：模型负责理解用户语言、识别歧义，并在受限 capability 集合中判断下一步需要哪类证据；确定性代码负责 Tool allowlist、状态约束、参数验证、循环限制、eligibility、金额、审批与写入。

模型输出不得包含任意 endpoint/SQL，也不得直接决定 refund eligibility 或 amount。

典型输出应是受限结构，例如：

```json
{
  "action": "CALL_TOOL",
  "tool": "get_logistics",
  "reasonCode": "NEED_LOGISTICS_STATE"
}
```

而不是直接给出“退款 299 元”或某个任意内部 URL。

**原因**：这既保留 Agent 的证据驱动决策价值，又把高风险边界留在确定性代码中。

## 决策 15 — 模型供应商不写死，但实现阶段先支持一个

**决定**：配置层记录 `MODEL_PROVIDER`、`MODEL_NAME`、`MODEL_TEMPERATURE` 等；实现只需先支持一个 OpenAI-compatible provider，不为了“多模型兼容”额外造复杂抽象。

Eval Run 必须记录模型配置，以保证数字可追溯。

## 明确拒绝的技术/功能

核心范围拒绝：

- Multi-Agent；
- Kafka/Event Bus；
- Kubernetes；
- 强制 Redis；
- 独立向量数据库；
- Model Fine-tuning / RLHF；
- 真实支付网关；
- 广义客服、售前推荐、营销、采购模块。

## Research Exit Verdict

当前设计已经足以进入实现准备阶段，但实现开始前必须保持以下三点明确：

1. checkpoint/migration ownership 不得与第三方框架实际行为冲突；
2. `decide_next_evidence` 必须遵循“模型建议、确定性边界约束”的混合机制；
3. 最终 Eval 必须记录模型配置，并对有明显非确定性的 routing case 做稳定性验证。

除此之外，不再增加新的规划层。