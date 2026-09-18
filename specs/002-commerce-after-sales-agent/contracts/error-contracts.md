# CommerceAgent Error Contracts

错误必须是稳定、机器可读的信号。Agent 应根据 error semantics 分支，而不是解析自然语言错误消息。

## 标准错误 Envelope

```json
{
  "errorCode": "ORDER_FORBIDDEN",
  "message": "Order is not accessible to the authenticated user",
  "retryable": false,
  "traceId": "...",
  "details": {}
}
```

## Error Taxonomy

| Code | 含义 | 可重试 | Agent 处理 |
|---|---|---:|---|
| `AUTH_REQUIRED` | 缺少或无效认证 | 否 | 停止，要求有效 session |
| `ACCESS_DENIED` | 已认证，但当前角色/权限不允许访问该能力 | 否 | 安全停止，不把角色拒绝误报成订单越权 |
| `ORDER_NOT_FOUND` | 订单不存在 | 否 | 澄清/重新搜索当前用户订单或停止 |
| `ORDER_FORBIDDEN` | 订单属于其他用户/拒绝访问 | 否 | 安全停止，不泄露订单细节 |
| `AMBIGUOUS_ORDER` | 存在多个合理候选订单 | 否 | 询问澄清，禁止写入 |
| `INVALID_ORDER_STATE` | 当前订单状态不允许该售后动作 | 否 | 重新评估路径，不强行写入 |
| `LOGISTICS_UNAVAILABLE` | 物流依赖不可用 | 有限 | 在预算内重试，否则转人工/安全停止 |
| `POLICY_NOT_FOUND` | 找不到合适政策证据 | 条件 | 确定性规则足够时可继续，否则升级人工 |
| `POLICY_VERSION_CONFLICT` | 无法确定有效政策版本 | 否 | 安全停止/人工复核，不任意选文本 |
| `ELIGIBILITY_DENIED` | 确定性规则拒绝动作 | 否 | 解释拒绝，不写入 |
| `MANUAL_REVIEW_REQUIRED` | 规则要求人工处理 | 否 | 创建工单/升级人工 |
| `APPROVAL_REQUIRED` | 资格允许但需要审批 | 否 | 创建/等待审批，不执行业务写入 |
| `APPROVAL_DENIED` | 人工审批拒绝 | 否 | 停止拟执行写入并反馈结果 |
| `APPROVAL_EXPIRED` | 审批已过期 | 否 | 仅在仍合理时重新发起审批 |
| `INVALID_PARAMETER` | 参数未通过 schema/业务校验 | 否 | 从权威证据修正参数，否则停止 |
| `AMOUNT_EXCEEDS_ALLOWED` | 请求金额超过后端计算上限 | 否 | 不猜金额，使用权威金额 |
| `IDEMPOTENCY_CONFLICT` | 同 key 被用于冲突 payload | 否 | 停止并检查既有逻辑动作 |
| `DUPLICATE_AFTER_SALES` | 已有冲突退款/退货 | 否 | 查询现有售后状态并据此返回/改路 |
| `WRITE_TIMEOUT_UNKNOWN` | 写请求超时，提交结果未知 | 禁止直接重试 | 先 `get_after_sales_status`，确认安全后才可同 key 重试 |
| `DEPENDENCY_TIMEOUT` | 读/决策依赖超时 | 有限 | 预算内重试，之后安全停止/升级 |
| `DEPENDENCY_UNAVAILABLE` | 必要依赖不可用 | 有限 | 重试后安全停止/升级 |
| `TOOL_NOT_ALLOWED` | 模型尝试调用未注册能力 | 否 | 阻止并记录安全/Tool Selection 失败 |
| `MAX_STEPS_EXCEEDED` | Agent 超过最大步骤预算 | 否 | 安全停止/升级，禁止继续循环 |
| `REPEATED_NO_PROGRESS` | 相同 Tool/参数重复且无新证据 | 否 | Circuit Break + 安全停止/升级 |
| `POST_WRITE_VERIFICATION_FAILED` | 写入返回成功但最终状态无法验证 | 禁止盲重试 | 查询权威状态；仍无法确认则标记未知并升级 |
| `PROMPT_INJECTION_BLOCKED` | 输入/检索内容试图修改受保护权限或策略 | 否 | 仅按正常权限继续，否则安全停止 |
| `INTERNAL_ERROR` | 未分类内部错误 | 条件 | 不进行不安全续跑，记录 trace 并失败关闭 |

## Handling Rules

1. `retryable=true` 不代表无限重试，每个 Tool 必须有有限 retry budget。
2. Write Error 比 Read Error 更保守；`WRITE_TIMEOUT_UNKNOWN` 绝不能直接转成新 write。
3. Authorization / Eligibility Error 对当前 proposed action 为终止性错误，除非权威业务状态之后发生变化。
4. Prompt Text 不能把 forbidden/non-retryable error 变成允许动作。
5. Error Code 必须进入 `ToolExecution` / `AgentRun` Trace 与 Eval failure taxonomy。
6. UI 可以本地化 message，但代码分支只依赖稳定 error code / status。
