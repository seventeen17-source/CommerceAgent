# CommerceAgent Tool Contracts

Agent Tool 是受控业务能力，不是任意 HTTP 访问。Python Agent 可以选择 Tool，但 ownership、eligibility、amount、state transition、approval 和 idempotency 的最终权威仍属于 Java Business Service。

## 统一 Tool Envelope

所有 Tool 返回统一结构：

```json
{
  "success": true,
  "data": {},
  "errorCode": null,
  "retryable": false,
  "latencyMs": 42,
  "traceId": "..."
}
```

全局规则：
- Tool 不接受模型输出的任意 URL、SQL 或内部服务名；
- authenticated principal 来自应用上下文，不来自 prompt；
- Read/Write Tool 分开注册并标注 risk level；
- 每个写 Tool 携带 `run_id` 和稳定 idempotency context；
- 写超时后必须先查询权威业务状态再决定是否重试；
- Trace 中只记录已校验参数/结果摘要，并最小化敏感数据；
- 审批通过权威 `approvalRequestId` 表示，Agent 不得生成或声明 approved token/state。

## T1 `list_user_orders`

**用途**：解析自然语言中的模糊订单引用。

输入：
- 可选 `created_after`
- 可选 `product_query`
- 可选 `status_filter`

输出：
- `order_id`
- 商品摘要
- 下单时间
- fulfilment status

风险：read / privacy medium。

禁止：模型传入任意 `user_id`。

## T2 `get_order`

**用途**：读取权威订单快照。

输入：`order_id`

输出：
- ownership-validated order status
- items/category
- amount/currency
- timestamps
- current after-sales state

错误：`ORDER_NOT_FOUND`、`ORDER_FORBIDDEN`、`DEPENDENCY_UNAVAILABLE`。

## T3 `get_logistics`

**用途**：读取权威物流状态和事件。

输入：`order_id`

输出：
- shipment status
- signed flag
- last meaningful event/time
- deterministic anomaly projection（如有）

规则：依赖不可用时不得编造 anomaly state。

## T4 `policy_search`

**用途**：检索有效售后政策/SOP 证据。

输入：
- normalized query
- 可选 product category
- 可选 scenario tag
- effective date context

输出：
- document code/title/version
- section/chunk text
- effective metadata
- retrieval score
- citation id

边界：检索文本只能解释政策，不能授权资金或状态写入。

## T5 `check_after_sales_eligibility`

**用途**：确定性判断退款/退货资格。

输入：
- `order_id`
- normalized reason code
- 可选 structured evidence references

输出：
- `eligible`
- `allowed_action`: `REFUND_ONLY | RETURN | RETURN_REFUND | MANUAL_REVIEW | DENY`
- `max_refund_amount`
- `approval_required`
- `rule_code`
- `rule_version`
- reason codes

权威：Java Backend。

禁止：模型覆盖 eligibility 或 amount。

## T6 `create_refund_request`

**用途**：创建唯一、经过校验的 RefundRequest。

输入：
- `order_id`
- `reason_code`
- requested amount
- `idempotency_key`
- 可选 `approval_request_id`

输出：
- refund request id
- accepted amount
- current status

风险：high write。

前置条件：
- authenticated owner；
- current order state 合法；
- eligibility 重校验通过；
- amount 合法；
- 如需审批，`approval_request_id` 必须指向同一 run/order/action/amount 且 `APPROVED` 的权威记录；
- 不存在冲突售后状态。

重试：禁止 blind retry。未知 timeout 后先查状态；只有安全时才允许同 key 重试。

禁止：跨用户退款、金额升级、审批绕过、模型生成 approval state/token。

## T7 `create_return_request`

**用途**：创建经过校验的退货/退货退款流程。

输入：
- `order_id`
- `reason_code`
- 可选 return method
- `idempotency_key`
- 可选 `approval_request_id`

输出：
- return request id
- state
- return deadline/instructions（如适用）

前置条件：deterministic return eligibility、ownership、当前状态/窗口检查，以及需要时的权威审批记录校验。

## T8 `create_support_ticket`

**用途**：自动化无法安全继续时升级人工。

输入：
- 可选 `order_id`
- issue category
- structured evidence summary
- source/citation refs
- urgency

输出：ticket id / status。

禁止保存 hidden chain-of-thought，只保存明确证据与结构化 reason code。

## T9 `request_human_approval`

**用途**：为高风险售后动作创建 Human-in-the-loop 审批。

输入：
- `run_id`
- `order_id`
- proposed action
- amount/risk summary
- evidence refs

输出：
- `approval_request_id`
- authoritative status = `PENDING`

禁止：Agent self-approval、伪造 approval status、生成 synthetic approval token，或把审批决策 endpoint 暴露为 customer Tool。

## T10 `get_after_sales_status`

**用途**：验证写入与恢复未知结果。

输入：
- `order_id`
- 可选 refund/return/ticket id
- 可选 idempotency reference

输出：现有售后对象与状态。

规则：任何可能已提交但返回 timeout 的 write，在再次发起写请求前必须先调用该 Tool。

## Tool Selection Policy

Agent 只能在已注册能力中基于证据选择下一步。至少要支持：

- logistics anomaly → refund；
- delivered item → return；
- ambiguous order → clarification / no write；
- high-risk eligible action → approval；
- evidence unavailable / manual review → escalation / safe stop。
