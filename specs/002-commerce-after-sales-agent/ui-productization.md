# US7 可信售后工作台与执行展示设计

本文定义目标界面、数据来源与交互；不记录完成状态。任务与验收见 [tasks.md](tasks.md)，唯一阶段入口见 [PROJECT_PROGRESS.md](../../PROJECT_PROGRESS.md)。

## 产品目标与范围交换

将 US1–US5 的自然语言理解、证据驱动分支、安全写入、人工协作、异常恢复和可追溯结果变成可操作、可核对的产品体验。以 US7 替代本轮 US6 政策检索投入：T064–T070 整体延期，完整登录体系、独立 Eval Dashboard、真正实时执行流不进入本轮。T071–T083 保留编号与验收责任；UI Gate 不代表最终作品集 Gate。

## 页面与信息架构

三个主入口：售后助手（默认）、执行演示、人工审批（按角色展示）。技术调试仍可进入原 Flow Playground。客户主页面加详情抽屉即可，不发展成电商后台。

### 售后助手

- 顶部：项目定位、当前身份、环境标记、演示配置入口。凭据仅内存持有，切换身份清空客户数据；不把密钥打包进前端。
- 左侧主工作区：欢迎说明、示例诉求（填入输入框后由用户发送）、对话、候选订单卡、补充输入、结果卡。
- 右侧：选中订单摘要、物流事实、处理依据、安全检查、下一步建议。内容随当前任务变化，历史消息与当前任务分开绑定。
- 无图片订单卡：商品摘要、订单号、创建时间、订单状态；金额从详情读、物流从物流接口读。没有字段时明确未获取，不能编商品图、分类、单价、运输轨迹。
- 多候选只能选本次有效候选；确认后旧按钮显示已确认并禁用。信息加载失败可重查读接口，不能因此重新创建 Run。
- 请求执行期间只显示“正在处理”；响应后展示真实阶段和执行回放。不得使用计时器假装节点推进或虚构百分比。
- 结果卡分别表达退款申请、退货申请、待审批、已转人工、安全停止、执行失败、结果未知；退款申请创建不等于到账，安全停止不等于创建工单。
- 待审批显示查询最新状态与继续原任务；拒绝、过期、资格漂移提供明确解释。重复点击和迟到响应不得污染其他 Run。

### 执行演示

- 场景目录：物流异常退款、签收转退货、订单歧义、高风险审批、依赖不可用、人工工单、写入响应丢失。每项解释要验证的优势、适用 fixture 和预期断言；预期与实际分栏。
- 主区域：真实执行时间线、选中节点的证据来源/业务动作/状态、权威业务结果；可并排对比两个真实 Run，说明相同诉求如何因不同证据改变路径。
- 安全边界面板：订单归属、资格、金额、审批、重复写防护、写后核验。每项展示事实状态、依据来源、关联任务及观测时间（有来源才展示）。机制存在与本次检查通过分开表达。
- 恢复演示：未知写入 → 权威查询 → 同一逻辑请求恢复或停止。只有真实 trace 支持时才能标记经历过恢复，普通成功不能套用恢复动画。
- 复用 Playground 上方场景/故障注入、左侧主链、右侧 STEP DETAIL；已有 T016 等验证入口必须继续可达。场景 reset 只对隔离 test/eval 环境开放，客户入口不可访问。
- 演示报告显示真实 case、Run、环境、版本、结果及证据链接。没有实际报告时显示“尚无报告”，不显示虚构成功率、节省成本或零风险指标。

### 人工审批

- 左侧待办列表与可解释空态；右侧订单、动作、金额、风险原因、规则依据、绑定与有效期。
- 批准/拒绝二次确认；以 Java 返回事实更新，超时先查询，不能乐观变绿。
- 客户与审批员的会话隔离；前端隐藏入口不替代后端授权。
- 客户恢复仍由 Agent 重新读取审批、重验资格、执行并核验；审批页面不能代客户绕过 Agent 直接退款。

## 页面文字线框（T084 交付物 · 可审阅稿）

本节只描述**目标界面**：每个页面有哪些区域、每个区域显示什么、在哪些状态下显示什么文案。字段的权威来源、权限与所需增量见下节矩阵；本节不记录实现进度。

### 通用外壳

- 顶部细横条：左＝产品名与当前入口名；中＝身份与环境（例 `customer-001 · dev · 真实服务`）；右＝「演示配置」抽屉按钮（凭据仅内存持有）。
- 入口切换沿用现有分段控件，不新引路由：**售后助手（默认）/ 执行演示 / 人工审批**；原 `Flow Playground` 仍作为独立入口可达，能力不迁移、不删减。
- 视觉：明亮灰白底、白底卡片 + 细描边 + 浅阴影；主操作用蓝色实心，危险动作（拒绝）用红色描边；颜色只出现在状态徽标与描边上，且始终配文字或图标。
- 所有编号（Run ID / 订单号 / 申请号 / 工单号）用等宽字体并可换行；基准 1440×900，1280×800 收窄右侧栏，390×844 时右侧栏改为底部抽屉。

### 售后助手（客户视角）

左右 ≈ 7:5 分栏。

| 区域 | 内容 | 状态与文案要点 |
|---|---|---|
| 左：欢迎区 | 一句话说明 + 3–4 个示例诉求按钮 | 按钮只把话填进输入框，由用户自己发送；不自动发起 Run |
| 左：对话流 | 用户气泡（右，浅蓝）/ 助手气泡（左，白底） | 执行期间只显示「正在处理…」；**无假进度、无计时器推进、无虚构百分比** |
| 左：候选订单卡 | 商品摘要、`订单号 · 创建时间 · 订单状态`；详情再补金额与类别 | 无图片即留空；多候选只能选本轮有效候选；选中后按钮变「已确认」并禁用，后续在**同一 Run** 续跑 |
| 左：结果卡 | 退款申请 / 退货申请 / 待审批 / 已转人工 / 安全停止 / 执行失败 / 结果待确认（七种形态） | 各自独立徽标与文案；「退款申请已创建 ≠ 已到账」；「安全停止 ≠ 已创建工单」；失败区分「未产生写入」与「结果未知」 |
| 左：结果卡底部 | `Run …` 小字，可展开回放 | 未知结果只给「重新核对」，**不给「重发」** |
| 右：订单摘要 | 订单号、状态、创建时间、金额（有字段才显示） | 缺字段显示「未获取」，不推测 |
| 右：物流事实 | 最近有效事件、停滞时长、来源与观测时间 | 区分「当次快照」与「刚刚刷新」 |
| 右：处理依据 | 命中规则码 + 人话解释 | 解释来自 Java 确定性规则，不是模型散文 |
| 右：安全检查 | 订单归属 / 资格 / 金额 / 审批 / 重复写防护 / 写后核验，六行五态 | 五态＝通过 / 阻断 / 未知 / 未检查 / 不适用；**空值显示「未检查」，绝不显示绿色** |
| 右：下一步建议 | 一句话（补充信息 / 等待审批 / 无需操作） | — |

异常路径：读取失败只提供「重试读取」，**不因此重新创建 Run**；刷新后清空客户数据并提示「请重新提供身份凭据后继续」，不回填上一身份的订单或 Run。

### 执行演示（原 Flow Playground 同一页面向上生长）

保持既有三区结构，新增能力落在既有区块内，不按任务纵向另开区块。

- **上方场景区**（沿用并追加按钮）：物流异常退款、签收转退货、订单歧义、高风险审批、依赖不可用、人工工单、写入响应丢失。每个按钮附一行说明「验证什么优势 / 适用 fixture / 预期断言」，点开后「预期 / 实际」分栏。
- **左侧调用链**：按**真实节点顺序**展示 `understand → resolve_order → decide_evidence → execute_evidence → check_eligibility →(request_approval)→ refund_write / return_write → verify → finalize`，旁路节点 `waiting_user / waiting_approval / safe_stop / escalate_or_safe_stop` 单独标注。**未走过的节点显示为灰色，不标完成**。
- **右侧 STEP DETAIL**：当前节点的输入、处理、输出、真实请求控件与原始响应（可折叠）。
- **安全边界面板**：六项检查的事实状态 + 依据来源 + 关联任务 + 观测时间（有来源才展示）；明确区分「机制存在」与「本次检查通过」。
- **恢复演示**：未知写入 → 权威查询 → 同一逻辑请求恢复或停止，三段式；只有真实 trace 支持时才标注「经历过恢复」。
- **并排比较**：两条真实 Run 的时间线并排，标出「同一诉求、证据不同、路径分叉」的位置。
- **演示报告区**：真实 case / Run / 环境 / 版本 / 结果与证据入口；没有报告时只显示「尚无报告」，**不显示成功率、节省成本、零风险等数字**。
- 页脚常驻一行：`回放（不是实时流） · 明细可能已按保留策略回收`。

### 人工审批（按角色展示）

- 左：待办列表，每行 `订单号 · 动作 · 金额 · 等待时长`；顶部状态筛选；空态文案「当前没有待审批的高风险动作」。
- 右：决策详情——订单与动作、金额、风险原因、命中规则码、绑定的审批请求 ID 与有效期，以及一句「本次为什么需要人」。
- 底部：拒绝（描边）/ 批准（实心，二次确认弹窗复述订单与金额）。决策后**不做乐观更新**，以 Java 返回事实刷新；超时或冲突时按钮消失并提示「请先刷新状态」。
- 本页永不出现「直接退款」：批准只表示授权，执行仍由 Agent 读取审批、重验资格、写入并核验。

### 全局状态与文案（每页都必须有）

| 状态 | 文案 / 表现 |
|---|---|
| 加载中 | 骨架或「正在读取…」，不显示上一次的旧值 |
| 空态 | 解释「这里为什么是空的」+ 一个可执行的下一步 |
| 执行中 | 「正在处理…」，无百分比、无节点动画 |
| 成功 | 说明**权威确认了什么**，而不是「操作成功」 |
| 失败 | 失败类型 + 是否产生写入 |
| 安全停止 | 停止原因 + 「未产生任何写入」 |
| 已转人工 | 工单编号 + 创建时间，不写成「已解决」 |
| 结果未知 | 「请求可能已提交，正在核对权威状态」+ 重新核对入口 |
| 明细已回收 | 「本 Run 的明细已按保留策略回收」+ 仍可看到的状态迁移 |
| 无权限 / 非本人资源 | 与「不存在」不可区分；不出现任何他人订单或 Run 的痕迹 |

### 仅能执行后展示的内容（不得提前渲染）

真实结果卡内容、`Run` 的真实终态与 `stopReason`、安全检查各项结论、证据摘要、工具调用与耗时、审批请求 ID 与实际决策、工单编号、回放时间线——这些必须等真实接口返回后才渲染；任何占位、示例或推断值都不得出现在客户界面与演示报告中。

## 可信展示数据矩阵（T084 冻结稿）

原则表（字段名以本节 A 表为准，实施时不再改名）：

| 展示 | 权威来源 | 缺失/未知处理 |
|---|---|---|
| 候选订单 | Agent 候选 ID + Java 本人订单/详情 | 不扩大为其他用户订单，不猜缺失字段 |
| 物流事实 | 本次已收集物流证据或显式刷新 Java | 区分当次快照与当前查询，注明来源 |
| safetyChecks | 已持久化结构化事实的确定性投影 | PASSED/BLOCKED/UNKNOWN/NOT_CHECKED/NOT_APPLICABLE；空值绝不默认通过 |
| evidenceSummary | 类型白名单中的订单/物流/资格事实 | 不透传任意 evidence.data、用户原文、隐藏推理 |
| stopReason | 当前 Run 的终态 checkpoint reason_code | 不用 errorCode 代替；保留策略回收时明示不可得 |
| result | 动作类型 + 实际业务资源 + 确认依据 | 区分退款/退货/工单，不能统称 refund ID |
| 执行路径 | owner-scoped checkpoint 与 tool trace | 明确回放，不宣称实时推送 |

展示投影不授权写入，不新增模型调用；Java 继续负责身份、资格、金额、审批和事务。退款/退货的 VERIFIED_SUCCESS 与工单创建响应确认是不同证据强度，不能把工单响应包装成独立回读核验。新字段与 OpenAPI、实现、测试同批交付并按 AGENTS.md 升版；本设计阶段不提前修改已发布契约。

### A. 子字段级来源矩阵

「今天由哪个接口给出」描述的是**接口现状**，不是任务完成状态。

| 展示值 | 页面子字段 | 权威来源（path:line） | 今天由哪个接口给出 | 所需增量（归属） |
|---|---|---|---|---|
| ① 候选订单 | 候选订单 ID 列表 | `AgentState.candidate_order_ids` → `AgentRunView.clarification.candidateOrderIds`（`agent-service/app/api/runs.py:182,263-265`、`agent-service/app/agent/state.py:283`） | `GET /api/v1/agent/runs/{runId}`（契约 `contracts/agent-api.openapi.yaml:181-198`） | 无 |
| ① 候选订单 | 澄清原因（意图不识 / 多候选 / 候选均不匹配） | `runs.py:250,262` | 同上 | 无 |
| ① 候选订单 | 商品摘要 / 订单号 / 订单状态 / 创建时间 | Java 列表读模型 `OrderSummary`（`commerce-backend/src/main/java/com/seventeen17/commerceagent/order/OrderSummary.java:17`，由 `order/OrderService.java:195-202` 生成） | `GET /api/v1/orders`（`order/OrderController.java:29`，CUSTOMER） | 无（前端用候选 ID 与本端点交叉核对，不扩大范围） |
| ① 候选订单 | 金额 / 币种 / 逐行商品类别 | Java 详情读模型 `OrderSnapshot`（`order/OrderSnapshot.java:21-22,36`） | `GET /api/v1/orders/{orderId}`（`order/OrderController.java:34`） | 无（金额只在详情；列表不带金额是刻意的） |
| ② 物流事实 | 物流状态 / 是否签收 / 最近有效事件时间 / 停滞时长 | `LogisticsSnapshot`（`logistics/LogisticsSnapshot.java:19-26`；停滞算法 `logistics/LogisticsStallCalculator.java:43-55`） | `GET /api/v1/orders/{orderId}/logistics`（`logistics/LogisticsController.java:29`） | 投影需标注「本次快照 / 当前查询」（T086） |
| ② 物流事实 | 最近一条物流事件内容 / 承运商 / 运单号 | DB 有（`resources/db/migration/V001__core_schema.sql:113-114`、`:90-91`），读模型**不出口**（`logistics/LogisticsService.java:59-61`） | 无 | 本期不显示；要显示须单列增量（不在 T084–T095 内） |
| ③ safetyChecks | 订单归属 | `AgentState.resolved_order_id`（`agent/state.py:288`） | **不出口**（`AgentRunView` 无该字段：`runs.py:149-190`） | T086 |
| ③ safetyChecks | 资格 / 金额上限 / 是否需审批 / 规则码 | Agent 侧 `EligibilitySnapshot`（`state.py:133-157`）；Java 侧同名事实 `eligibility/EligibilityDecision.java:38-46` | Agent 侧**不出口**；Java 侧仅 `POST /api/v1/after-sales/eligibility` 返回 | T086（Run 级投影） |
| ③ safetyChecks | 审批绑定是否核验 | `ApprovalSnapshot`（`state.py:160-191`，含 `binding_verified`） | **不出口** | T086 |
| ③ safetyChecks | 重复写防护 | `WriteIntent`（`state.py:221-253`） | **不出口**，且**不得外泄幂等键/指纹原文**；页面只表达「同一逻辑请求」 | T086（布尔或枚举） |
| ③ safetyChecks | 写后核验结论 | `VerificationOutcome`（`state.py:256-269`）→ `verificationStatus`（`runs.py:179-181`） | ✅ 出 | 无（`NOT_CHECKED` / `NOT_APPLICABLE` 两态需 T086 补） |
| ④ evidenceSummary | 订单 / 物流 / 资格三类结构化事实 + 观测时间 | `AgentState.evidence`（`state.py:290`）、`EvidenceItem`（`state.py:117-130`）；白名单构造范式见工单摘要 `agent/nodes.py:639-664` | **不出口**（`AgentRunView` 刻意不发布 `state_json`：`runs.py:150-156`） | T086（类型白名单，LOGISTICS 起步） |
| ⑤ stopReason | 终态停止原因 | `agent.agent_checkpoints.reason_code`（`V002__agent_run_checkpoint.sql:78`；写入 `agent/runtime.py:160-170`；读回 `trace/store.py:456-483` → `trace/checkpoint.py:251`；取值 `agent/routing.py:84-103`） | **不出口**：`_timeline()` 构造事件时丢弃该列（`runs.py:477-486`），`AgentRunView` 无字段 | T085（禁止用 `errorCode` 代替） |
| ⑥ result | 动作类型（退款 / 退货 / 转人工） | `EligibilitySnapshot.allowed_action`（`state.py:141`）、`WriteIntent.action`（`state.py:246`）、`RunRecord.final_action`（`trace/checkpoint.py:130`） | 只出原始动作名 `finalAction`（`runs.py:176`） | T085（转为展示分类） |
| ⑥ result | 退款资源编号 | `agent/verify_business_state.py:111-118` | 出，但字段名为 `verifiedRefundRequestId`（`runs.py:183-185,296-305`） | T085：按动作拆分或改名（**当前退货号也会被塞进这个字段**） |
| ⑥ result | 退货资源编号 | `verify_business_state.py:196-202`；Java `returns/ReturnResult.java:15` | Agent 侧无独立字段；Java 创建响应给出 | T085 |
| ⑥ result | 工单编号与创建确认 | `AgentState.support_ticket_id`（`state.py:295`，仅 `OPEN` 时写 `nodes.py:702-707`）；Java `support/SupportTicketResult.java:4` | Agent 侧**不出口**；Java 仅创建响应给出 `ticketId`+`status`，**无 GET 可回读** | T085（Run 级）；Java 回读端点本期不新增 |
| ⑥ result | 确认依据强度 | `routing.py:493-504`（权威回读 vs 工单创建响应） | 只有 `verificationStatus`（`runs.py:179-181`） | T085（区分 `VERIFIED_READBACK` 与 `WRITE_RESPONSE_CONFIRMED`） |
| ⑦ 执行路径 | 状态迁移 + 工具调用（节点 / 状态 / 时间 / 延迟 / 工具错误码） | `agent.agent_checkpoints`（`store.py:456-483`）+ `agent.tool_executions`（`store.py:420-454`） | `GET /api/v1/agent/runs/{runId}/trace`（`runs.py:528-538`）；`/events` 为**有限重放**（`runs.py:507-525`） | 回放补 `reasonCode`/`nextAction`/`retryCount`/`riskLevel`/`traceId`/工具输入输出摘要（T092） |
| ⑦ 执行路径 | 事件类型覆盖 | 契约声明 9 种 `eventType`，生产只 emit `STATE_TRANSITION` 与 `TOOL_CALL`（`runs.py:204-214` vs `:480,490`） | 只有 2 种 | T092：要么收敛契约，要么让 `WRITE`/`VERIFICATION`/`APPROVAL` 真正产生 |

### B. 页面动作 → 接口映射（按钮不允许「待定」）

| 页面动作 | 接口 | 角色 / ownership | 失败时页面表现 |
|---|---|---|---|
| 发送诉求（创建 Run） | `POST /api/v1/agent/runs`（`runs.py:409-455`） | 任意已认证；未配模型 → 503 且不落库 | 「当前无法开始处理」；不留 Run |
| 补充信息（澄清续跑） | `POST /api/v1/agent/runs/{runId}/input`（`runs.py:541-573`） | owner-scoped（403 / 404） | 保留原问题，不新建 Run |
| 审批后继续原任务 | `POST /api/v1/agent/runs/{runId}/resume`（`runs.py:576-610`；内部重读 Java 审批并重校验绑定 `:613-704`） | owner-scoped | 「审批未通过或已过期」+ 不写入 |
| 查看当前任务 | `GET /api/v1/agent/runs/{runId}`（`runs.py:458-465`） | owner-scoped | 无权限与不存在不可区分 |
| 回放执行路径 | `GET /api/v1/agent/runs/{runId}/trace`（`runs.py:528-538`） | owner-scoped | 明细已回收 → 「已按保留策略回收」 |
| 选单（候选订单卡） | `GET /api/v1/orders` + `GET /api/v1/orders/{orderId}`（`order/OrderController.java:29,34`） | CUSTOMER；owner 进 SQL 谓词 | 加载失败 → 「重试读取」，不重建 Run |
| 物流事实 | `GET /api/v1/orders/{orderId}/logistics`（`logistics/LogisticsController.java:29`） | CUSTOMER | 「未获取」或明确不可用 |
| 审批待办列表 | `GET /api/v1/approvals?status=`（`approval/ApprovalController.java:40`） | **APPROVER**；全局队列、无 ownership | 空态文案 |
| 审批决策 | `POST /api/v1/approvals/{approvalId}/decision`（`approval/ApprovalController.java:47`） | **APPROVER**；按 id 决策；同决策幂等、改判 409 | 按钮消失 + 「请先刷新状态」 |
| 客户查看自己的审批引用 | `GET /api/v1/approvals/{approvalId}`（`approval/ApprovalController.java:35`） | **CUSTOMER**（owner-scoped） | 不可读 → 引导回任务卡 |

四条必须写进页面设计的权限事实：

1. **APPROVER 读不到订单与物流**：`/api/v1/orders/**` 一律要求 CUSTOMER（`security/SecurityConfig.java:41-42`）→ 审批台**只能**显示审批行自带字段（`orderId`、`actionType`、`amount`、`riskReason` 码、`eligibilityRuleCode`、`expiresAt`），并明确提示「订单明细需客户身份」，不得留白或猜测。
2. **APPROVER 读不到单条审批详情**：`GET /approvals/{approvalId}` 要求 CUSTOMER（`SecurityConfig.java:55-56`）→ 审批台只用列表接口。
3. **`SUPPORT` 角色今天没有专属权限**（`SecurityConfig` 内无 `hasRole("SUPPORT")`）→ 本期不存在「客服视角」页面，也不新增该角色。
4. **没有登录端点**（`security/LocalJwtIssuer.java:12` 仅 dev/test/eval；`SecurityConfig.java:86-92`）→ 身份仍由「演示配置」抽屉粘贴凭据，是本轮有意的范围。

### C. 状态判定与文案依据

| 页面状态 | 判定依据 | 文案方向 |
|---|---|---|
| 已核验成功 | `verificationStatus=VERIFIED_SUCCESS`（`runs.py:179-181`）+ 业务资源引用 | 说明**权威确认了什么**，不写「操作成功」 |
| 已核验失败 | `VERIFIED_FAILURE`（或业务拒绝码，如 `DUPLICATE_AFTER_SALES`） | 「未产生资金动作」 |
| 结果未知 | `verificationStatus=UNKNOWN` 或写响应丢失 | 「可能已提交，正在核对权威状态」+ 重新核对（不是重发） |
| 安全停止 | `status=SAFE_STOP` + T085 的 `stopReason` | 「已安全停止」+ 原因 + 未产生写入 |
| 已转人工 | `status=ESCALATED` + 工单引用（T085） | 「已转人工」+ 工单编号；不写「已解决」 |
| 明细已回收 | `checkpointCompactedAt != null`（`runs.py:188-190`、`trace/checkpoint.py:141`；回收规则 `trace/retention.py:86-112`、`trace/store.py:751-775`） | 「本 Run 明细已按保留策略回收」；`stopReason` 明示不可得 |
| 无权限 / 非本人 | owner 谓词未命中：Agent 侧 403 `RUN_FORBIDDEN`（`runs.py:398`）；Java 侧统一 404 隐藏存在性 | 与「不存在」不可区分 |

### D. 请求超时后 Run 识别（本设计的明确决定）

- 现状：`runId` 只在 `POST /runs` 响应里返回；Agent 侧只有 owner-scoped 的单条查询，**没有「按身份列出我的 Run」的端点**；Java 侧没有任何以 run 为维度的查询端点（`@RequestParam` 仅 `approvals.status` 与 `refunds.idempotencyKey` 两处）。
- 本期决定：**不新增查询标识**。响应丢失且无 `runId` 时，不盲发新 Run，显示「无法确认本次请求的结果」与恢复边界（对应 `tasks.md` T089 的验收项）。
- 将来若要做「按身份列出自己的 Run」：属**新端点 + 契约语义变更**，必须先在 T084 登记并单列范围，不得借 T085/T086 顺带加入。

### E. 所需增量清单（按归属任务）

| 增量 | 内容 | 归属 |
|---|---|---|
| `stopReason` | 终态 `reason_code` 提升到 run 视图；回收时明示不可得 | T085 |
| `result` 投影 | `{actionType, resourceKind, resourceId, confirmation}`，退款 / 退货 / 工单分开 | T085 |
| 修正 `verifiedRefundRequestId` | 退货号不再塞进退款字段（拆分或改名，保留旧字段兼容） | T085 |
| `safetyChecks[]` | 六项五态确定性投影，能表达「机制未运行」，空值绝不默认通过 | T086 |
| `evidenceSummary` | 类型白名单投影（LOGISTICS 起步）+ 观测时间 + 来源标记 | T086 |
| 回放补字段 | `reasonCode` / `nextAction` / `retryCount` / `riskLevel` / `traceId` / 工具输入输出摘要 | T092 |
| 事件类型 | 契约 9 种 vs 生产 2 种：收敛契约或真正产生事件 | T092 |
| 契约与代码同批升版 | `contracts/agent-api.openapi.yaml`（现 `0.2.2`）按 §10 判定 patch / minor，并在 devlog 点名 | T085 / T086 / T092 |

### F. 本期明确不做（页面必须降级，而不是留白或猜）

| 缺口 | 本期处理 |
|---|---|
| `APPROVER` 读订单 / 物流（403） | 审批台只显示审批行字段，并标注「订单明细需客户身份」 |
| 工单回读端点（只有创建响应） | 结果卡展示创建响应里的 `ticketId` + `status`，注明「以创建响应为确认依据」 |
| `SUPPORT` 角色工作台 | 本期不存在，不新增角色 |
| 登录 / 会话 | 继续手工凭据 + 身份切换，不新增登录页 |
| 按状态列出 Run / 跨用户统计 | 本期不做；执行演示只回放**已知 Run ID** |
| 物流事件内容 / 承运商 / 运单号 | 本期不显示（读模型不出口） |
| 规则码的可读解释文案 | Java 不提供文案；由前端按枚举映射，并在页面注明「解释来自规则码映射」 |

## 视觉与可借鉴机制

明亮灰白底、蓝色主操作、清晰卡片层次；复杂路径通过渐进展开呈现。绿/橙/红/灰都配文字与图标，键盘可操作，长编号可换行。优先验收 1440×900、1280×800、390×844，窄屏把证据区改为抽屉。

以下是前期源码/README 调研形成的机制参考，不代表已逐帧观看全部演示或证明样式促成获奖：

| 参考作品 | 借鉴 | 本项目落点 |
|---|---|---|
| [SmartScribe](https://github.com/woziji2200/SmartScribe) | AI 嵌入任务工作区、上下文操作 | 对话、订单、证据和结果在同一工作台 |
| [BrainDance](https://github.com/tianxingleo/BrainDance) | 结果与来源、后续动作组合 | 结果卡可展开证据，并指向可执行下一步 |
| [通慧智教](https://github.com/TochusC/ai-assistant-teaching-website) | 按角色与业务对象组织入口 | 客户/演示/审批明确分工 |
| [慧眼识瑕](https://github.com/Anionex/pcb-defect-detection-app) | 核心任务到结果详情的短路径 | 选单、执行、核验详情的连续交互 |
| [Mai-Duo-Duo](https://github.com/mango7789/Mai-Duo-Duo) | 总览与详情联动 | 场景结果点击定位真实 Run，拒绝装饰性指标 |

丰富度来自可探索的真实信息：订单、物流、证据、分支、安全边界、恢复过程、业务结果及审计关联；不靠增加无关菜单或虚构图表。

## UI Gate 验收矩阵

每行记录 fixture 版本、输入、身份、Run ID、UI 截图、实际接口结果、业务状态/Trace 证据及 pass/fail。模拟测试不能替代真实跨服务结果。

| 场景 | 页面预期 | 业务/机制断言 |
|---|---|---|
| 未收到包裹 | 物流事实 → 退款申请已核验 | 恰一申请且金额正确；不写到账 |
| 已签收 | 路径转退货、返回退货编号 | 退货存在且禁止直接退款 |
| 两笔候选 | 无图订单卡 → 同 Run 续跑 | 确认前零写；过期卡不可提交 |
| 高风险审批 | 等待 → 审批员决策 → 客户继续 | 批准前零写；拒绝/过期/错绑定不执行 |
| 依赖失败 | 原因可见、停止、无伪造工单 | 零退款/退货/工单，有限重试 |
| MANUAL_REVIEW | 工单创建确认与真实编号 | 恰一 OPEN 工单 + 同事务审计 |
| 写响应丢失 | 核对结果提示与恢复路径 | 先读权威、同 key 恢复、无重复写 |
| 跨用户/切身份/刷新/断网 | 无泄露、无旧结果覆盖、明确恢复边界 | 后端拒绝越权；未知写不能重新发起当重试 |

开发命令与逐 T 完成标准见 tasks.md。最终完整作品集仍须执行原 T078–T083 等交付验收，不能以截图替代。
