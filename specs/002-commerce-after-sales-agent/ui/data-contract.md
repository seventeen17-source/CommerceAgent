# UI-1.0 数据、权限与实施接缝

## 核对范围与证据性质

2026-10-13执行git fetch --all --prune成功。读取工作区分支feat/customer-workspace-shell，HEAD b6c1639c70b7e5d39933f6a6a850f1eb659d4035；远端集成线origin/dev/002-commerce-after-sales-mvp为e8cca70e8928215c23edb68921be4d9a01df7276。本文是设计所需接口核对，不是US1–US5完整生产验收。工作区有他人未提交登录与UI代码，本轮未修改/测试它们。以下行号指本轮读取时内容；后续Agent必须重新定位。

## 已读取的接口事实

| UI对象/动作 | 生产/契约证据 | 使用约束 |
|---|---|---|
| 创建Run | agent-service/app/api/runs.py:113、409；CreateRunRequest.message上限4000 | body只有message，不发送假orderId字段；身份来自认证 |
| Run摘要 | 同文件:149、224、458 | runId/status/intent/resolvedOrderId/currentNode/nextAction/finalAction/finalMessage/approvalRequestId/verificationStatus/version/checkpointCompactedAt |
| 候选订单 | 同文件:253、268 | clarification.kind/candidateOrderIds；仅等待用户时返回 |
| 结果引用 | 同文件:296 | verifiedRefundRequestId读取verification.resource_id；不能凭字段名断言资源就是退款；T085统一投影 |
| Trace | 同文件:193、468、528 | node/toolName/status/errorCode/latencyMs/summary/timestamp；输入输出详细摘要需T092增量 |
| 事件 | 同文件:507 | SSE封装的是已持久化事件有限重放，不是实时订阅 |
| 补充/恢复 | 同文件:541、576、613 | 同Run input/resume；等待审批恢复重读Java审批绑定，前端不能传APPROVED |
| Run权限 | 同文件:707 | store.get_run_for_owner，APPROVER不是自动跨owner运营读取 |
| 本人订单 | commerce-backend/src/main/java/com/seventeen17/commerceagent/order/OrderController.java:29、34；contracts/commerce-api.openapi.yaml:585 | 列表productSummary/status/createdAt；详情totalAmount/currency/items；无图正常 |
| 审批列表/决定 | commerce-backend/src/main/java/com/seventeen17/commerceagent/approval/ApprovalController.java:40、47 | GET /api/v1/approvals?status=…；POST /api/v1/approvals/{id}/decision body decision=APPROVE或DENY |
| 审批字段 | contracts/commerce-api.openapi.yaml:772 | runId/orderId/actionType/amount/riskReason/eligibilityRuleCode/status/requestedAt/expiresAt/decidedBy/decidedAt |
| 客户审批重读 | ApprovalController.java:35；Agent runs.py:613 | owner审批读取与APPROVER全局列表不是同一权限 |

HTTP真实前缀：Agent /api/v1/agent；Java /api/v1。Web开发proxy /agent与/commerce是代理别名，不是部署API标准。

实际检索：`rg -n '^class |^def |^async def |@router|verificationStatus|result:|safetyChecks|stopReason|evidenceSummary|currentNode|orderId|status:' agent-service/app/api/runs.py`；`rg -n '^  /|^    [A-Za-z].*:|enum:|version:' specs/002-commerce-after-sales-agent/contracts/agent-api.openapi.yaml`。在这些范围内未发现Run列表或运营汇总路由；不能据此将整个仓库其他分支判为不存在。

读取SecurityConfig.java的工作区版本仍限制订单GET为CUSTOMER、审批list/decision为APPROVER。该文件及commerce OpenAPI有未提交登录增量，不能称“没有登录”，也不能称登录已验收。旧设计此类绝对结论作废。

## 展示字段的确定性来源

- 订单归属：授权订单读取/明确安全投影；仅有resolvedOrderId不能让浏览器自判PASSED。
- Evidence：T086白名单投影，给值、来源类型、来源引用、observedAt可空、历史快照标识。不透传任意payload。
- Rule：Java资格的ruleCode/ruleVersion/reasonCodes/allowedAction/approvalRequired；未发布阈值时显示“规则要求人工审批”，不猜300。客户只看解释，企业可展开规则码。
- Decision：Agent拟执行动作与Java允许动作分开；前端不重新算资格。
- Action Boundary：T086安全投影PASSED/BLOCKED/UNKNOWN/NOT_CHECKED/NOT_APPLICABLE；空值不是通过，不适用需明确事实。
- Verification：T085 result={actionType,resourceKind,resourceId,confirmation}目标投影；confirmation区分VERIFIED_READBACK与WRITE_RESPONSE_CONFIRMED；工单响应不能标独立回读。stopReason来源终态checkpoint，不用errorCode代替。
- 请求摘要/Owner/时间：没有来源不补写。Runtime owner是客户，负责人是工作分配概念；未有分配记录显示“负责人未提供”。
- P04业务快照、P05审批证据、P06恢复明细、P07统计均需各自授权的只读投影，不能在浏览器拼接客户凭据绕过访问限制。

## 目标增量（提案，不是已发布API）

归T097契约设计、T098实现；只读运营范围采用现有APPROVER作为受控本地演示运营读角色，经Java /me确认。CUSTOMER无权跨owner；不新增浏览器自选Admin。该最小模型仅面向项目单组织环境，多租户不在本轮。运营读取不赋予客户write/input/resume权限；Java订单接口不直接全局放开。

| 目标接口 | 字段最低合同 | 页面 |
|---|---|---|
| GET /api/v1/agent/operations/runs | items[{runId,status,intent,resolvedOrderId,currentNode,startedAt,updatedAt,verificationStatus,recovered,needsAttention}],nextCursor,asOf,scope | P01/P03/P06；status/from/to/cursor/limit，limit默认20最大100 |
| GET /api/v1/agent/operations/runs/{id} | 脱敏RunView + T085/T086安全投影 + displayRequestSummary可空；不输出原始state/token | P03/P04；服务端角色校验和最小字段 |
| GET /api/v1/agent/operations/runs/{id}/trace | T092结构化事件；稳定eventId、发生时间、节点/工具/摘要、恢复证据 | P03/P06；权限与详情一致 |
| GET /api/v1/agent/runs（owner列表） | 同一用户items,nextCursor,asOf；不接受任意ownerId | P02我的任务；不解决未知ID首POST与列表关联的可靠性问题 |
| GET /api/v1/agent/operations/metrics | windowStart/windowEnd/timezone/asOf/scope；N,T,V,A,H,R,S及failureGroups与来源样本 | P01/P07；口径见pages；空分母返回null |
| GET /api/v1/cases/{runId}（owner）及 /api/v1/operations/cases/{runId}（APPROVER） | 受权关联的order/logistics/afterSales摘要；来源时间；明确missing/unknown；纯读 | P04；Java以现有业务记录核对绑定，未有业务绑定则不暴露任意订单 |
| GET /api/v1/operations/approvals/{id}/context | 审批绑定对象的最小证据及规则说明；客户敏感字段省略 | P05；仅APPROVER，绑定来源为审批记录，不接受任意orderId替换 |

上述路径在T097核对现有契约命名后锁定；如需调整，必须同批修改本表、任务和消费者映射，不能静默猜端点。接口增量需最小设计评审、契约升版、所有权/角色负例、production wiring与查询证据，不以mock通过代替。Java仍是commerce唯一权威，Agent不能直查commerce表。详情数据暂缺时前端保留区域，禁止假装全量运营中心已完成。

T085/T086/T092的新增字段只在实现、契约、测试同批发布时可依赖；不提前改OpenAPI版本。

## 不新增命令的明确决策

- 审批只用现有decision；审批成功后客户通过现有resume继续，不从企业端冒充客户。
- Recovery为可审阅执行记录及业务状态，刷新只读取，不发起退款重试、不解除终态SAFE_STOP。
- 人工接管显示已创建工单或停止上下文；没有接单命令不能显示“接管成功”。
- 首POST响应丢失且未知runId不能盲重发；Run列表即使存在，也不能按“最近一条”猜关联。可靠client request key应另立任务，不偷塞本轮。
- 不增加SSE实时生命周期、不增加支付结算、不增加商品图片、不增加草稿存储和取消业务命令。

## DTO消费约束

界面适配器只从已发布字段读；未知枚举降为UNKNOWN并保留诊断码，禁默认成功。日期ISO转Asia/Shanghai显示，金额按currency格式，不由商品文本猜货币。长ID禁止截断后用截断值调用API。历史快照时间和GET获取时间分开。所有敏感字段需白名单及递归泄露测试。
