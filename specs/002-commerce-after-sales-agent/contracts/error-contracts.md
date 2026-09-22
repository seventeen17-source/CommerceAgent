# CommerceAgent Error Contracts

错误必须是稳定、机器可读的信号。Agent 应根据 error semantics 分支，而不是解析自然语言错误消息。

## 标准错误 Envelope

```json
{
  "errorCode": "ORDER_NOT_FOUND",
  "message": "The order does not exist or is not accessible to the authenticated user",
  "retryable": false,
  "traceId": "...",
  "details": {}
}
```

## Ownership Concealment Rule（T019）

**订单不存在**与**订单属于其他用户**必须产生**完全相同**的响应：相同状态码（`404`）、相同 `errorCode`
（`ORDER_NOT_FOUND`）、相同 `message`。实现不得为其中一种情况补一句"更友好"或"更精确"的提示。

理由：错误码的字面语义会附带事实。`403` 的字面含义是"资源**存在**，但你无权访问"，因此它顺带回答了"这个
id 存不存在"。本项目订单 id 形如 `order-001`，是可枚举的；把这两种情况分开，读接口就变成攻击者的**存在性
预言机**（existence oracle）。

因此：

- `403` 在两个 customer read 端点上**只**表示"已认证主体缺少该端点所需的角色/能力权限"，对应
  `ACCESS_DENIED`。它**绝不**用于 ownership 失败。
- `ORDER_FORBIDDEN` **已从本契约删除**：它描述的是"订单属于其他用户"这一场景，而该场景按上述规则必须与
  "不存在"不可区分，因此它没有合法的生产方。保留一个没有合法出口的错误码，只会诱导后来的实现者重新引入
  存在性泄露。
- **对外抹平不等于内部失明**：后端仍必须把**真实原因**写入结构化安全审计
  （`commerce.audit_logs`，`action = ORDER_ACCESS_DENIED`，`metadata.reason = CROSS_OWNER`）。这不是可选装饰 ——
  否则"谁在探测别人的订单"将永远无法被回答。
- 审计写入**失败不得改变对外结果**：若只有 cross-owner 路径会写审计，那么"审计写失败 → 500"会重新变成区分
  两种失败的信号。请求本来就要被拒绝，此时丢掉的只是可观测性，不是业务动作，因此应记录 ERROR 日志后仍抛出
  统一的 `ORDER_NOT_FOUND`。

## 评估结论 vs 错误（T020）

"资格不符合"不是错误，"评估无法完成"才是错误。这两件事必须由不同的通道表达，否则 Agent 会把一次依赖故障或一次
越权探测当成业务结论：

| 情形 | 通道 | 形态 |
|---|---|---|
| 评估完成，结论是**批准**某动作 | 成功 | `200` + `EligibilityDecision`（`eligible=true`、引用规则行、给出金额上界） |
| 评估完成，结论是**拒绝** | 成功 | `200` + `eligible=false`、`allowedAction=DENY`、`reasonCodes` 说明原因 |
| 评估完成，结论是**无法自动决定** | 成功 | `200` + `eligible=false`、`allowedAction=MANUAL_REVIEW`、`reasonCodes` 说明缺什么 |
| 越权 / 订单不存在 | 错误 | `404 ORDER_NOT_FOUND`（两者不可区分，见上） |
| 订单状态与规则前提冲突 | 错误 | `409 INVALID_ORDER_STATE` |
| 权威依赖不可用（如规则要求物流证据但没有运单） | 错误 | `503 LOGISTICS_UNAVAILABLE`（有限重试） |

因此：

- `ELIGIBILITY_DENIED`、`MANUAL_REVIEW_REQUIRED`、`APPROVAL_REQUIRED`、`AMOUNT_EXCEEDS_ALLOWED` 是**写路径**
  错误：它们在提交前重校验一个 proposed action 时拒绝该 action，而不是在评估阶段表达"不符合资格"。
- 任何"把 `503`/`404` 降级成一个 `eligible=false` 决策"的实现都是错的：那会把"不知道/看不到"永久固化成
  "业务上不允许"。
- 反过来，把 `eligible=false` 当成请求失败（例如抛出 `500`）同样是错的：它是一次成功且权威的回答，Agent 应当
  据此解释拒绝或转人工，而不是重试。

## Error Taxonomy

| Code | 含义 | 可重试 | Agent 处理 |
|---|---|---:|---|
| `AUTH_REQUIRED` | 缺少或无效认证 | 否 | 停止，要求有效 session |
| `ACCESS_DENIED` | 已认证，但当前角色/权限不允许访问该能力 | 否 | 安全停止。它**只**表示角色/能力不足，绝不代表资源归属问题 |
| `ORDER_NOT_FOUND` | 订单不存在**或**不属于当前主体（两者刻意不可区分） | 否 | 澄清/重新搜索当前用户订单或停止；不得据此推断该 id 是否存在 |
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
| `EVAL_CASE_NOT_FOUND` | Eval fixture case/version 不存在 | 否 | Eval Runner 将 case 标为 dataset/config error |\n| `EVAL_RESET_CONFLICT` | 另一个 reset transaction 正在执行 | 有限 | Eval Runner 延迟后有限重试 |\n| `EVAL_RESET_FAILED` | fixture reset 基础设施失败 | 否 | 标记 infrastructure failure，不归因于模型 |\n| `INTERNAL_ERROR` | 未分类内部错误 | 条件 | 不进行不安全续跑，记录 trace 并失败关闭 |

## Handling Rules

1. `retryable=true` 不代表无限重试，每个 Tool 必须有有限 retry budget。
2. Write Error 比 Read Error 更保守；`WRITE_TIMEOUT_UNKNOWN` 绝不能直接转成新 write。
3. Authorization / Eligibility Error 对当前 proposed action 为终止性错误，除非权威业务状态之后发生变化。
4. Prompt Text 不能把 forbidden/non-retryable error 变成允许动作。
5. Error Code 必须进入 `ToolExecution` / `AgentRun` Trace 与 Eval failure taxonomy。
6. UI 可以本地化 message，但代码分支只依赖稳定 error code / status。
7. 越权读与"不存在"必须不可区分（见 Ownership Concealment Rule）。Agent 不得把 `ORDER_NOT_FOUND` 解读为
   "这个 id 有效但不属于我"——它拿不到这个信息，也不应该尝试通过重试或改变措辞来获取它。
8. 安全拒绝事件必须写结构化审计并保留真实原因；但审计子系统的可用性**不得**影响对外响应的一致性。
