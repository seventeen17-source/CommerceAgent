# Runtime contracts：工具、恢复、错误与测试接口

本文件定义语义，两份 OpenAPI 定义 HTTP 形状；修改接口须同时修改调用方/测试。不存在独立的旧 tool/error/eval 契约。以下全部是编码要求，非已实现能力。

## 1. 协议与身份

Java /api/v1；Python /api/v1。业务 API 使用 camelCase，Python 内部 snake_case 由 Pydantic alias 显式映射。JSON 请求拒绝未知字段。UUID 用实际 UUID，不把 customer-001 等展示名传给 UUID 列。金额整数分，currency=CNY。

两个服务验证固定 alg/issuer/audience/exp/subject；Java 业务层检查有效用户及资源所有权。客户看不到其他客户的订单/run/操作/审批；返回一致的 RESOURCE_NOT_FOUND，不能先暴露存在再报无权限。审批列表/决定仅 APPROVER。客户即使猜到 approvalId，也必须通过订单所有者检查。

JWT 只存在本次请求 runtime context，经受控 httpx client 传给 Java；不进入 LLM、checkpoint 或 trace。审批人凭据不用于推进客户图。开发环境仅 localhost；Web 令牌只保存在内存，刷新重新登录/粘贴测试令牌，不写 URL/localStorage/构建产物。CORS 只允许指定本地 origin。

## 2. 图与工具边界

DecisionPolicy 接收经过裁剪的 State 与当前允许工具列表，返回一个工具提议或 ASK_USER/DENY/SAFE_STOP。模型工具 arguments 经严格 schema 与业务对象集合校验；一次只能接受一个工具调用。不把 reasoning 文本当控制信号；记录工具、证据引用、原因码即可。

| 内部工具 | 映射 | 模型能提供的参数 | 程序注入与前置条件 |
|---|---|---|---|
| list_user_orders | GET /orders | productQuery，可空 | 当前 JWT，最多 20 个候选；更多匹配则澄清 |
| get_order | GET /orders/{orderId} | orderId | 必须来自用户输入或当前候选，Java 再查所有权 |
| get_logistics | GET /orders/{orderId}/logistics | 已解析 orderId | Java 返回权威时间/状态 |
| check_after_sales_eligibility | POST /after-sales/eligibility | 已解析 orderId，reasonCode | 标准原因枚举；用户声称缺陷不构成可退款事实 |
| get_policy_document | 本地 manifest 精确读取 | 无；或已验证的 code/version | 使用资格返回的 policyCode/policyVersion；路径由 allowlist 映射 |
| request_human_approval | POST /approvals | 无保护性参数 | 使用已保存的订单/动作/原因/版本，runId/operationId 程序生成 |
| create_after_sales_request | POST /after-sales/requests | 无保护性参数 | 使用冻结的资格上下文与必要 approvalId；Java 独立再校验 |
| get_after_sales_request | GET /after-sales/requests/{requestId} | 不给模型任意选择 | verify 节点使用权威 operation 返回的 requestId |
| get_operation | GET /operations/{operationId} | 不给模型任意选择 | 恢复控制器使用本 run 的稳定 operationId |
| get_approval | GET /approvals/{approvalId} | 不给模型任意选择 | 恢复控制器使用本 run 保存的审批记录 |

前七项是阶段受限的提议能力；后三项由确定性恢复/验证代码强制执行，不靠模型自愿调用。写提议只有在唯一订单、资格允许、必需证据齐备且用户目标明确时进入可用集合。用户要求退款与退货路径冲突且需要额外行动时，应解释/澄清而不是隐瞒；创建退货申请不视为用户已寄回。

understand/resolve/evidence loop → check eligibility → risk gate → prepare operation → write → verify → finalize。read 结果标明来源/版本/时间。资格与模型路径不一致时，拒绝模型写提议并返回权威原因，不修改后端规则。

## 3. 明确预算（初始可调，比较时冻结）

每 run 最多 30 个图步骤、10 次模型请求（含共享 NLU/格式纠正/重试）、24 次工具尝试、20000 个累计模型 tokens、4 次用户澄清输入。模型每次 30 秒、输出 512 tokens；read/decision HTTP 3 秒，最多 1 次重试；write HTTP 5 秒，未知结果先查 operation，最多 1 次同键原 payload 重发。SDK/httpx 隐式重试关闭，所有尝试进入计数与 trace。

每次推进最多 180 秒主动执行时间，等待用户/审批不计入；跨恢复的模型/步骤计数不重置。达到任一预算 SAFE_STOP；危险写已发出但未核实则显示 outcome=UNKNOWN，不能声称未写或失败退款。读重试退避 0.2 秒；持续失败不循环。重复相同证据请求且无新增信息连续 2 次停止。

## 4. 可查询的幂等写入

Java 创建审批、创建售后均要求 Idempotency-Key=operationId(UUID)，由 Python 在 prepare 节点生成并先 checkpoint。body 在发出前冻结并保存规范化 hash；包括 runId/orderId/actionType/reasonCode/expectedOrderVersion/ruleCode/ruleVersion/approvalId（如需）。身份来自 JWT；金额不在请求 schema。

键作用域(userId, operationId)。同键同 payload 返回原业务结果；同键不同 payload 为 IDEMPOTENCY_CONFLICT。后端在订单行锁与一个事务中提交对象、操作结果、状态变更和审计；不同键同订单由 order_id UNIQUE 约束拒绝第二个售后申请。

GET operation 返回 SUCCEEDED（kind/resourceId）或 ABSENT。ABSENT 仅表示暂时不可见，旧请求可能仍在处理；只允许同键原 payload 受限重试，不能生成新键。确认 SUCCEEDED 后还要 GET 业务对象并匹配订单/动作/金额，才输出成功。反复不可查时记录 UNKNOWN 并停止自动推进；后续人工/客户查询可澄清，不能再次创建新申请。

已提交同键结果的返回顺序：先身份/所有权/请求 hash 检查，再返回既有结果；不要因订单已被第一次请求改为 REQUESTED 就错误拒绝合法重放。没有既有结果时才重新进行最新资格/审批校验。

审批创建不同键但相同 run/action fingerprint 的重复请求，应在订单锁内返回既有 PENDING/APPROVED 审批并记录新 operation 到同一资源；拒绝/过期记录不会被悄悄改回 PENDING。V1 过期停止当前 run，用户新请求才能申请新审批。审批决定用资源状态幂等：同一审批人重复相同决定返回原值，冲突决定 409；CONSUMED 不允许再决定。

## 5. 澄清与重启

thread_id=run_id；官方 checkpoint 是图状态权威，AgentRun 是可重建索引。运行期间通过 PostgreSQL session advisory lock 保护同一 run 的一个推进者，专用连接持锁，finally 释放；崩溃连接关闭后释放。不要跨 LLM 调用持有数据库事务。长时间并发 continue 返回 RUN_BUSY，不能创建第二个执行图。

POST run 使用 clientRequestId 去重；POST input 使用 inputId+payload hash 去重，并要求 expectedStateVersion。先检查已处理的同 inputId，再判断新输入是否过期。图中 applied_input_ids 与数据库输入收据协调，防止 checkpoint 已成功而收据失败时重复应用。continue 不注入新输入；终态返回当前视图；WAITING_USER 必须通过 input；WAITING_APPROVAL 先用客户身份查询 Java。

官方 interrupt 恢复会重跑节点起始部分。因此不得在 interrupt 前无条件创建审批或随机新键；准备操作、外部执行和等待节点分离，副作用一律走幂等 API。至少测试业务提交后 checkpoint 前强制退出，重启只核实/重放原操作而不是发起新业务。

## 6. 审批授权快照

Java 根据实时业务状态计算金额、规则版本、订单版本和 fingerprint。审批请求中的 actionType/reasonCode 只是提议，必须等于资格允许结果。批准不能覆盖 DENY/不兼容状态；执行时验证 owner/run/order/action/reason/amount/currency/version/expiry，事务内消费 APPROVED→CONSUMED。

客户可读取自己的单条审批（解决恢复的读路径），只有 APPROVER 可列待办和决定。审批创建支持同键重放。审批人 UI 展示后端给出的动作/金额/原因，不把模型摘要当权威。已有售后/订单版本变化/规则变化时 STALE_ACTION，停止而不消费旧批准。

## 7. 稳定错误契约

HTTP 错误统一 {errorCode,message,retryable,traceId}。Python 工具归一化为 {success,data,errorCode,retryable,traceId,latencyMs}；应用分支只看码。retryable 不代表任意重试，更不能作用于未知写入。

| Code | 常见 HTTP / 来源 | 行为 |
|---|---|---|
| AUTH_REQUIRED | 401 | 停止，需要新的有效身份 |
| RESOURCE_NOT_FOUND | 404 | 不泄露他人资源；澄清或停止 |
| ROLE_FORBIDDEN | 403 | 禁止客户审批；不更换身份绕过 |
| INVALID_PARAMETER | 422 | 最多一次按权威证据纠正，不猜保护字段 |
| ELIGIBILITY_DENIED | 422 | DENIED，无写入 |
| MANUAL_REVIEW_REQUIRED | 422/资格值 | SAFE_STOP，提示联系人工，未创建工单 |
| APPROVAL_REQUIRED | 422 | 创建/等待审批；M1 未实现审批时 SAFE_STOP |
| APPROVAL_DENIED | 409 | DENIED，不能发起相同写入 |
| APPROVAL_EXPIRED | 409 | SAFE_STOP，当前 run 不自动循环申请 |
| STALE_ACTION | 409 | 不使用旧资格/审批；记录需重新发起 |
| IDEMPOTENCY_CONFLICT | 409 | 停止，不换键掩盖冲突 |
| DUPLICATE_AFTER_SALES | 409 | 查询已存在申请，不能写第二条 |
| DEPENDENCY_UNAVAILABLE | 503 | 只读有限重试后停止 |
| WRITE_TIMEOUT_UNKNOWN | Python 网络映射 | 查 operation，按原键恢复；非普通 retryable |
| POST_WRITE_VERIFICATION_FAILED | Python 验证 | UNKNOWN，保留 request/operationId，不谎报成功 |
| INPUT_CONFLICT / STALE_INPUT / RUN_BUSY | 409 | 显示当前 run；不重复推进/注入 |
| TOOL_NOT_ALLOWED / BUDGET_EXCEEDED / REPEATED_NO_PROGRESS | Python 控制器 | 阻断、记录并 SAFE_STOP |
| INTERNAL_ERROR | 500 | 记录脱敏错误，不能继续资金写入 |

HTTP 200 eligibility 合法返回 DENY/MANUAL_REVIEW，不把它误解成业务允许。没有“检测到了所有 prompt injection”的布尔保证；靠权限/参数/预算约束并计数被拦截的危险提议。

## 8. 仅评测内部接口（不在公开 OpenAPI）

只有 test/eval profile 注册，另校验 X-Eval-Key，Agent runtime/LLM/普通客户拿不到此密钥。仅本地 eval 网络可达，不通过 Web 暴露。

POST /internal/eval/fixtures/{fixtureId}/reset
body: {datasetVersion,fixtureVersion,evaluationNow}；全部必填且必须匹配预登记 manifest。
返回 {fixtureId,datasetVersion,fixtureVersion,evaluationNow}；清理本案例业务/操作/审批/审计并加载确定性订单。默认串行，运行中的 case 禁止 reset；冲突 409。

GET /internal/eval/fixtures/{fixtureId}/snapshot
返回 {orders,afterSalesRequests,approvals,operations,auditEvents} 完整权威投影，供 scorer 检查额外/隐藏写入；不是只查询 Agent 返回的 id。

POST /internal/eval/clock
body: {evaluationNow}；用于审批过期等测试，仅改业务 Clock，不修改 JWT 的真实时间。故障 schedule 由 fixture 定义（提交前延迟/提交后丢响应）；不允许任意 SQL、代码或 URL。不存在/坏版本 404/422，基础设施失败 500；记 infra failure，不冒充模型失败。
