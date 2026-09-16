<!--
同步影响说明
- 版本：模板占位 -> 1.0.0
- 将默认占位原则替换为 CommerceAgent 项目治理原则
- 新增：架构与安全约束、开发流程与质量门
- 后续实现必须遵循本 Constitution
-->

# CommerceAgent 项目宪法

## 核心原则

### I. 确定性业务权威
LLM/Agent 可以负责理解用户意图、消除歧义、判断下一步需要什么证据、从允许列表中选择 Tool，以及在后端已声明合法的业务路径中进行编排。

LLM/Agent **不得**成为以下事项的最终权威：订单归属、身份认证、授权、退款/退货资格、退款金额、合法状态迁移、审批要求、幂等性和事务是否成功。

任何资金或业务状态写入，在提交前都必须由 Java 后端基于当前权威业务状态重新校验。

**原因**：本项目要证明 Agent 的推理与编排价值，但不能把资金类和事务类授权交给概率模型或检索文本。

### II. 安全、幂等、可验证的写入
所有会改变业务状态的能力都必须具备：身份认证、授权、确定性业务校验、幂等控制、必要的事务一致性、审计记录和写后验证。

写请求超时或结果未知时，禁止盲目重试。必须先查询权威业务状态；仅当后端能证明不存在冲突写入时，才允许在同一逻辑幂等上下文中安全重试。

**原因**：一个可能重复退款，或没有验证最终状态就向用户宣称成功的 Demo，不属于可接受的企业 Agent 实现。

### III. 基于证据改变行为
Agent 必须维护显式任务状态，并根据当前证据选择下一步动作，而不是把所有“退款类表达”都送入固定流程。

同一句高层用户请求，在不同的业务种子状态下，必须能够产生实质不同的结果，例如：澄清、退款、退货、等待审批、升级人工、拒绝或安全停止。

Agent 必须有最大步骤数、最大重试预算和无新证据停止条件。

**原因**：这是项目的 **Agent Value Gate**。如果新证据无法改变下一步动作，那么该功能应实现为确定性工作流，而不是包装成 Agent 推理。

### IV. 用户输入、检索文本和模型输出均不可信
用户文本、检索得到的政策文本、模型生成的参数以及外部 Tool Result，在验证前都应视为不可信数据。

政策/SOP 检索只能提供解释、上下文和引用，不能修改认证信息、Tool allowlist、退款金额、资格判断、审批状态或后端权限。

Agent 不得通过模型输出任意内部 URL、SQL、服务名或可执行代码来绕过已注册 Tool。

**原因**：Prompt Injection 和受污染的检索内容必须在确定性边界处失败关闭（fail closed）。

### V. 测试、Eval 与 Trace 必须可复现
业务不变量和高风险路径在对应功能完成前必须有自动化测试。

Agent 行为必须在版本化、可重置的 fixture 上评估；能用确定性业务状态作为 oracle 时，不应依赖模型裁判。

Baseline 与 Agent 版本必须使用可比较的数据集版本、权限、重置状态和指标定义。

任何性能、安全、时延、成本或改进数字，只能在存在可复现运行产物时对外陈述。

Trace 必须记录结构化状态迁移、Tool、已验证参数摘要、结果/错误、重试、审批、写入和写后验证，但不得存储或展示隐藏 chain-of-thought。

### VI. 架构与范围必须克制
核心实现应保持能够证明业务系统与 Agent 边界的最小架构：

- 一个 Java 模块化单体；
- 一个 Python Agent 服务；
- 一个轻量 Web 客户端；
- 一个 PostgreSQL 实例。

除非有实际测量证据，否则核心范围不得引入微服务拆分、Kafka、Kubernetes、Redis 作为核心状态、独立向量数据库、Multi-Agent、真实支付/第三方生产集成或大范围电商功能。

**原因**：复杂度只有在解决已证明的问题时才有价值，而且必须能在 6–8 周个人项目中解释和交付。

## 架构与安全约束

- Java 负责权威 commerce state、业务不变量、授权、确定性 eligibility、合法状态迁移、幂等、审批校验、审计和事务写入。
- Python 负责 Agent state/orchestration、LLM 调用、allowlisted Tool adapter、政策检索、checkpoint/resume、结构化 Agent trace 与离线 Eval。
- Agent **不得直接读写** commerce 业务表；业务访问必须经过类型明确的 Java API。
- principal 必须来自应用安全层/JWT，不能从 prompt 推断；原始 token/credential 不得进入 prompt 或 trace。
- Human-in-the-loop 审批必须由后端权威 `ApprovalRequest` 表示。Agent 只能引用 `approvalRequestId`，不得自行声明审批已通过。
- 一个 PostgreSQL 可以包含多个逻辑 schema，但 schema ownership 与 migration ownership 必须明确，不能因为共享数据库而模糊服务权威边界。
- Eval fixture reset 接口只能存在于 test/eval profile。

## 开发流程与质量门

1. **先设计后实现**：`spec.md`、`plan.md`、data model、contracts 与 `tasks.md` 在开始实现前必须一致。
2. **高风险能力必须有测试**：授权、eligibility、状态迁移、幂等、超时恢复、审批、Prompt Injection 边界必须具备自动化测试。
3. **MVP Gate**：物流异常退款切片必须先完成 Agent → Java → PostgreSQL → 写后验证 → Trace 的端到端闭环，之后才能扩展可选框架/基础设施。
4. **Agent Value Gate**：项目被称为完成的 Agent 项目前，同一句退款类请求必须在不同 seed state 下至少覆盖退款、退货、澄清和等待审批等实质不同路径。
5. **Safety Gate**：冻结安全集内不得接受跨用户写入、审批绕过、重复逻辑退款/退货或模型自行授权的资金写入。
6. **Evidence Gate**：README/简历/Demo 中的数字必须链接到真实、版本化 Eval 输出；目标值不能写成已达成结果。
7. **范围变更规则**：核心纵向切片开始后，新增一个 Must-have 能力必须删除或延期同等规模的其他范围。

## 治理

本 Constitution 是 CommerceAgent 的最高项目级工程约束。Feature spec、implementation plan、task list 和代码评审都必须遵循它。

违反 MUST 规则的设计或实现，不能以“方便”“框架默认行为”或“模型能力更强”为理由绕过。

修改 Constitution 需要：
1. 写明修改原因和受影响原则；
2. 按语义化版本更新版本号；
3. 标明需要同步更新的 spec、plan、contracts、tasks、tests 和文档；
4. 如果修改改变现有 feature 边界，恢复实现前必须重新进行一致性分析。

版本规则：
- **MAJOR**：删除/重定义不可妥协原则，或改变权威/安全边界；
- **MINOR**：新增原则或显著扩大治理要求；
- **PATCH**：不改变行为要求的澄清。

每个实现 PR 至少检查：确定性业务权威、安全写入、Agent Value、输入/检索信任边界、可复现证据以及范围克制。

**Version**: 1.0.0 | **Ratified**: 2026-09-15 | **Last Amended**: 2026-09-16
