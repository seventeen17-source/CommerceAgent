# 数据、状态与事务模型

V1：合成订单；CNY；单商品摘要/单包裹；整单申请；每订单最多一个 after-sales request。金额使用整数分（Java long / SQL bigint），不使用二进制浮点。外部请求不能传入批准金额。

## Schema 与迁移

commerce：Java 业务权威。agent：Python 索引/trace/输入收据。checkpoint：官方 saver 的恢复状态，表结构不在此复制。Flyway 仅管理前两者；checkpoint-init 单独管理第三者。运行账号均无 DDL 权限，Python 无 commerce 读写权限。

## 自定义表

### commerce.users

id UUID PK；role CUSTOMER/APPROVER；status ACTIVE/DISABLED。只预置身份，不做注册或用户管理。JWT subject 必须匹配有效用户；Java 每次业务访问再次检查。

### commerce.orders

id UUID PK；user_id FK users；product_name；category STANDARD/ELECTRONICS/DIGITAL；amount_minor bigint 1..100000000；currency 固定 CNY；status SHIPPED/DELIVERED/CANCELLED；created_at timestamptz；delivered_at nullable；shipment_status；last_logistics_event_at nullable；logistics_events jsonb（只读合成轨迹）；after_sales_status NONE/REQUESTED；version bigint。

delivered 状态必须有 delivered_at。物流停滞只从固定业务时钟与权威事件推导，不信用户/模型声称“超过阈值”。一个订单只存一个包裹快照；不实现物流运营。业务写入锁定订单行，更新 version 与 after_sales_status。

### commerce.after_sales_requests

id UUID PK；order_id UNIQUE FK orders；user_id FK users；run_id UUID；action_type REFUND_ONLY/RETURN_REFUND；reason_code NOT_RECEIVED/UNWANTED/DEFECT_REPORTED；amount_minor bigint；currency CNY；status 固定 CREATED；operation_id UUID；approval_request_id nullable FK approvals；rule_code；rule_version；created_at。

amount_minor 必须等于本次后端资格决定的整单金额；order_id UNIQUE 是 V1 的跨 run/跨幂等键防重复约束。RETURN_REFUND 仅表示申请创建，未验证寄回/付款；无取消重开，不模拟完整资金账本。新记录与订单状态、操作结果、审批消费、成功审计在一个 Java 事务提交。

### commerce.approval_requests

id UUID PK；user_id/order_id/run_id；action_type；reason_code；amount_minor；currency；order_version；rule_code/rule_version；action_fingerprint；status PENDING/APPROVED/DENIED/CONSUMED/EXPIRED；expires_at；decided_by nullable；created_at/decided_at/consumed_at。

fingerprint 由 Java 对 user/order/run/action/reason/amount/currency/orderVersion/ruleVersion 的规范化序列哈希。期限为合成业务时钟创建后 15 分钟。PENDING→APPROVED/DENIED；PENDING/APPROVED 过期视为 EXPIRED；APPROVED→CONSUMED 仅在业务申请事务。重复相同人工决定返回原状态，冲突决定拒绝；DENIED/CONSUMED/EXPIRED 不回到 PENDING。写入时锁审批行且校验 fingerprint、期限与身份，不仅看一个 approved 布尔值。

### commerce.operation_records

复合 PK (user_id, operation_id UUID)；kind CREATE_AFTER_SALES/CREATE_APPROVAL；payload_hash；status SUCCEEDED；resource_id；response_json；created_at。

成功 operation 与业务对象同事务提交，无“先保存成功键、后业务失败”的窗口。事务尚未提交时查询可返回 ABSENT；ABSENT 只表示当前查询不可见，非未执行证明。相同键和规范化 payload 返回同一结果；不同 payload 为 IDEMPOTENCY_CONFLICT。并发依靠唯一键/订单行锁串行化，重复 run 使用新键仍受订单 UNIQUE 约束。

失败的业务校验不产生成功 operation；不记录可被误读成成功的占位。查询结果为 SUCCEEDED/ABSENT；持续未知时 SAFE_STOP 并显示待核对，不报告失败退款或自动换键。

### commerce.audit_events

id、actor_id、action、resource_id、run_id、operation_id、result、reason_code、occurred_at。只追加；重要成功写审计与业务事务一致，拒绝审计用独立受控路径，事务回滚不能吞掉拒绝记录。不存原始凭据和长篇用户敏感文本。

### agent.agent_runs

run_id UUID PK = thread_id；user_id；client_request_id UUID；request_hash；status；state_version bigint；current_node；final_action；final_message；result_request_id nullable；approval_id nullable；model_config_json（无密钥）；started_at/updated_at。UNIQUE(user_id, client_request_id)。重复创建同请求返回原 run；同键改文本冲突。

status：RUNNING / WAITING_USER / WAITING_APPROVAL / COMPLETED / DENIED / SAFE_STOP / FAILED。投影可由 checkpoint 重建，禁止用它授权业务或替代图恢复真相。

### agent.run_inputs

PK(run_id,input_id UUID)；payload_hash；payload_json（用户消息或候选订单，无凭据）；status PENDING/APPLIED；created_at。checkpoint 中保存 applied_input_ids。恢复在 run 锁内先读取图状态，再补应用尚未生效的输入；同 inputId 不重复注入；payload 变更拒绝。结果投影/收据写入失败可以从 checkpoint 协调，不二次执行业务写。

### agent.tool_executions

id UUID PK；run_id；sequence；tool_name；attempt；operation_id nullable；input_summary/output_summary；error_code；status；latency_ms；model_usage_json nullable；created_at。原始 token、密钥和隐藏思维链不落库。拒绝调用也要记录为 blocked attempt，区分工具没执行与业务拒绝。

## 版本化资源，而不是新平台

规则放 commerce-backend/src/main/resources/rules/after-sales-v1.yaml，固定 ruleCode/version/policyCode/version。类别 DIGITAL、缺陷自报或证据不足返回 MANUAL_REVIEW；有效普通物流异常允许 REFUND_ONLY；DELIVERED 七天内允许 RETURN_REFUND；取消/窗口外 DENY；金额 >=100000 分需要审批。阈值是本项目合成假设。

政策放 knowledge/policies/，manifest 包含 code/version/effectiveFrom/effectiveTo/section/path/checksum。后端返回准确代码/版本，Python 只从 manifest 允许路径读取。不得从模型输出拼文件路径。

## 图状态（官方 checkpoint 持有）

保存 user_id（非 JWT）、request、intent/reason、candidate_order_ids、resolved_order_id、证据值及 version/时间、eligibility、pending_action、approval_id、operation_id、冻结的请求 payload/hash、applied_input_ids、step/retry/model_call budgets、final result。不得持久化客户端、数据库连接、函数、密钥或模型私有推理。

执行顺序：understand → resolve/evidence loop → eligibility → approval gate → prepare_write/checkpoint → execute_write → verify → finalize。ASK_USER/WAITING_APPROVAL 使用官方 interrupt。write 节点重放沿用原 operationId 与 payload；不重新生成随机键。continue 前刷新权威订单/审批；变化导致 STALE_ACTION 时停止，不使用旧批准覆盖新状态。

## 事务顺序

先验证身份/请求 schema，再锁订单行；检查已提交 operation（同键同 payload 可返回原结果，但仍检查所有者）；计算最新资格；需要审批则锁并核对审批；插入申请、更新订单、消费审批、写 operation 与成功审计；一次提交。并发唯一冲突后重新读取既有结果并核对 payload，不能把所有 UNIQUE 错误当成功。

状态查询永不直接授予重试安全。查询 ABSENT 时仅允许原键原 payload 的受限再试；并发场景由同一事务/唯一约束保证。资金仍未实际划转。
