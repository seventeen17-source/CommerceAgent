# CommerceAgent 数据模型

该数据模型明确区分：权威 commerce state、Agent execution state、policy knowledge，以及 audit/eval records。

## 数据库与 Schema Ownership

本地为了简单复现使用一个 PostgreSQL 实例，但逻辑 ownership 必须清晰：

- `commerce`：权威业务表，语义 owner 为 Java backend；
- `agent`：`AgentRun`、`ToolExecution`、runtime trace/checkpoint metadata，语义 owner 为 Python Agent Service；
- `policy`：政策检索 metadata/chunk/vector，语义 owner 为 Python Agent Service；
- `eval`：可选 EvalRun/EvalResult metadata，语义 owner 为 Eval Runner / Agent Service。

Python **不得直接读写 `commerce` 业务表**；它访问权威业务状态必须经过类型化 Java API。

实际实现时应使用独立数据库 role/permission 强制服务边界，而不仅依赖代码约定。

---

## 1. User

字段：
- `id`
- `username`
- `role`: `CUSTOMER | APPROVER | SUPPORT`
- `status`: `ACTIVE | DISABLED`
- `created_at`

规则：
- Customer API 必须从认证 principal 得到 ownership，不接受模型传入的任意 `user_id`；
- Approval Decision 需要 `APPROVER` 角色。

## 2. Order

字段：
- `id`
- `user_id`
- `status`: `PAID | SHIPPED | DELIVERED | CANCELLED | CLOSED`
- `total_amount`
- `currency`
- `created_at`
- `shipped_at`
- `delivered_at`
- `after_sales_status`
- `version`（optimistic lock）

规则：
- ownership 不可变；
- 非法状态迁移由服务器拒绝；
- Order state 不得来自 RAG 或 model memory。

## 3. OrderItem

字段：
- `id`
- `order_id`
- `product_id`
- `product_name`
- `product_category`
- `unit_price`
- `quantity`

规则：退款资格和金额计算必须使用权威持久化价格。

## 4. Shipment

字段：
- `id`
- `order_id`
- `carrier`
- `tracking_number`
- `status`
- `last_event_at`
- `signed_at`
- `version`

关系：V1 中一个 Order 对应 0/1 个 Shipment；一个 Shipment 对应多个 `LogisticsEvent`。

## 5. LogisticsEvent

字段：
- `id`
- `shipment_id`
- `event_type`
- `description`
- `occurred_at`

规则：
- synthetic/local 环境下事件采用 append-oriented fixture；
- stall duration 根据权威时间戳确定性计算。

## 6. AfterSalesRule

结构化、可执行售后业务规则。

字段：
- `id`
- `rule_code`
- `version`
- `product_category`
- `required_order_status`
- `logistics_stalled_hours`
- `return_window_days`
- `max_refund_amount`
- `approval_threshold`
- `allowed_action`
- `active`
- `effective_from`
- `effective_to`

规则：
- 供 deterministic eligibility service 使用；
- 不得来自模型输出；
- 可以与人类可读的 `AfterSalesPolicy` 对应，但两者不是同一实体。

## 7. EligibilityDecision

确定性资格决策 Value Object，可按审计需要保存快照。

字段：
- `decision_id`
- `order_id`
- `eligible`
- `allowed_action`: `REFUND_ONLY | RETURN | RETURN_REFUND | MANUAL_REVIEW | DENY`
- `max_refund_amount`
- `approval_required`
- `rule_code`
- `rule_version`
- `reason_codes[]`
- `evaluated_at`

规则：
- 表示某一时刻的权威决策；
- 敏感写入前仍需重新校验；
- Agent 不得覆盖任何字段。

## 8. RefundRequest

字段：
- `id`
- `order_id`
- `user_id`
- `reason_code`
- `amount`
- `status`: `CREATED | PROCESSING | COMPLETED | REJECTED | CANCELLED`
- `idempotency_key`
- `eligibility_rule_code`
- `approval_request_id` nullable
- `run_id`
- `created_at`
- `updated_at`

约束：
- 同一逻辑写入范围内幂等键唯一；
- `amount` 不得超过确定性 eligibility 结果；
- 已有冲突售后状态时禁止创建；
- 如要求审批，`approval_request_id` 必须对应同一 run/order/action/amount 且状态为 `APPROVED` 的权威审批记录。

## 9. ReturnRequest

字段：
- `id`
- `order_id`
- `user_id`
- `reason_code`
- `status`: `CREATED | WAITING_SHIPMENT | RECEIVED | REFUND_PENDING | COMPLETED | REJECTED`
- `return_deadline`
- `idempotency_key`
- `approval_request_id` nullable
- `run_id`
- `created_at`
- `updated_at`

约束：
- 幂等规则与 RefundRequest 一致；
- 创建必须经过 deterministic return eligibility；
- 要求审批时执行与 RefundRequest 相同的 Approval Binding。

## 10. SupportTicket

字段：
- `id`
- `user_id`
- `order_id` nullable
- `category`
- `reason`
- `evidence_summary`
- `status`: `OPEN | IN_PROGRESS | RESOLVED | CLOSED`
- `run_id`
- `created_at`
- `updated_at`

规则：
- 当退款/退货不允许自动继续时仍可以安全创建工单；
- 只存结构化 evidence summary / reason code，不存隐藏 chain-of-thought。

## 11. ApprovalRequest

字段：
- `id`
- `run_id`
- `order_id`
- `action_type`
- `amount` nullable
- `risk_reason`
- `status`: `PENDING | APPROVED | DENIED | EXPIRED`
- `requested_at`
- `decided_at` nullable
- `decided_by` nullable

状态迁移：

`PENDING → APPROVED | DENIED | EXPIRED`

终态不能回到 `PENDING`。

规则：
- Agent 不能直接设置 `APPROVED`；
- 只有授权 approver endpoint 可以改变审批状态；
- 敏感写入只接受 `approval_request_id`，不接受模型生成的 approval token/status；
- 提交写入前重新读取审批记录并核对 run/order/action/amount。

## 12. AgentRun

字段：
- `run_id`
- `user_id`
- `status`: `RUNNING | WAITING_USER | WAITING_APPROVAL | COMPLETED | ESCALATED | FAILED | SAFE_STOP`
- `intent`
- `resolved_order_id` nullable
- `current_node`
- `next_action` nullable
- `step_count`
- `retry_count`
- `state_payload` / `state_json`（持久化 resume 所需最小显式状态）
- `final_action` nullable
- `error_code` nullable
- `model_name`
- `model_temperature`
- `prompt_version`
- `input_tokens`
- `output_tokens`
- `started_at`
- `completed_at` nullable

规则：
- 必须持久化足够状态支持 clarification/approval resume；
- 业务真相仅引用，不复制为 Agent 权威；
- Run 查询/恢复接口必须验证 authenticated ownership 或明确 operational role。

## 13. ToolExecution

字段：
- `id`
- `run_id`
- `step_index`
- `tool_name`
- `risk_level`
- `input_summary`
- `output_summary`
- `status`: `SUCCESS | ERROR | TIMEOUT | DENIED`
- `error_code` nullable
- `retryable`
- `latency_ms`
- `trace_id`
- `created_at`

规则：
- 敏感字段最小化/脱敏；
- 不保存原始 auth token。

## 14. AuditLog

字段：
- `id`
- `actor_type`: `USER | AGENT | APPROVER | SYSTEM`
- `actor_id`
- `action`
- `resource_type`
- `resource_id`
- `run_id` nullable
- `result`
- `metadata_json`
- `created_at`

规则：关键写入和 auth decision 必须产生结构化 audit event。

## 15. AfterSalesPolicy / PolicyDocument

`AfterSalesPolicy` 是领域概念：版本化、人类可读的售后政策/SOP。

持久化时可表示为 `PolicyDocument` 与 `PolicyChunk`。

`PolicyDocument` 字段：
- `id`
- `document_code`
- `title`
- `version`
- `category`
- `effective_from`
- `effective_to`
- `checksum`
- `source_path`
- `active`

约束：`(document_code, version)` 唯一。

## 16. PolicyChunk

字段：
- `id`
- `document_id`
- `section`
- `content`
- `embedding`（仅启用向量检索时需要）
- `metadata_json`

规则：
- 检索结果必须返回 parent document/version/effective metadata；
- Policy Text 不能直接授权业务写入。

## 17. EvalCase / EvalRun / EvalCaseResult

### EvalCase
- `case_id`
- `dataset_version`
- `dataset_split`
- `category`
- `user_task`
- fixture/reset identifier
- expected tool/action predicates
- forbidden actions
- expected business-state predicates
- tags

Case 定义存放在 Git 版本化文件中。

### EvalRun
- `eval_run_id`
- `dataset_version`
- `system_version`: `BASELINE | V1 | OPTIMIZED`
- `model_config`
- `git_commit`
- `started_at`
- `completed_at`

### EvalCaseResult
- `eval_run_id`
- `case_id`
- `run_id`
- task/tool/parameter/state/safety scorer results
- latency/token/tool-call counts
- failure taxonomy

V1 Eval 采用 CLI/file-first，结果写入 `eval/reports/`；核心不要求公开 Eval API。

---

## 关系摘要

```text
User 1---* Order 1---* OrderItem
              |
              0..1 Shipment 1---* LogisticsEvent
              |
              * RefundRequest
              * ReturnRequest
              * SupportTicket
              * ApprovalRequest

AgentRun 1---* ToolExecution
AgentRun --- Refund/Return/Ticket/Approval via run_id

AfterSalesPolicy
  -> PolicyDocument 1---* PolicyChunk

AfterSalesRule -> EligibilityDecision -> guarded write
```

## 关键状态规则

1. `AgentRun` 状态不是业务授权。
2. `EligibilityDecision` 是确定性决策，敏感写入前必须重新校验。
3. `WAITING_APPROVAL` 阶段禁止退款/退货创建，直到关联权威 `ApprovalRequest` 为 `APPROVED` 且 binding 一致。
4. 写入超时不代表失败；重试前必须先查询权威状态。
5. 同一逻辑幂等键不能创建多个逻辑退款/退货。
6. Policy/RAG 文本和 Agent prose 都不能直接修改 Order/Refund/Return 状态。
7. 一个物理 PostgreSQL 不等于共享业务权威；服务边界应由 API 与数据库权限共同强制。
