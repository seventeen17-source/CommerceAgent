# T032 — State-driven Agent Runtime Design

> **文档定位**：本文是 T032（LangGraph Assembly）的实现规格。它不推翻 `plan.md` 与既有 T031/T017 设计，只把"流程连接图"升级为"State-driven Runtime 设计"。
>
> **命名纪律**：本文出现的所有字段名、枚举值、表名、方法名一律取自当前代码。任何与代码不一致的名字都是缺陷，应改文档而不是改枚举。

权威来源（按优先级）：

1. `specs/002-commerce-after-sales-agent/plan.md`
2. `specs/002-commerce-after-sales-agent/tasks.md`（T032 条目）
3. `agent-service/app/agent/state.py`（`AgentState` 与四个枚举的唯一定义处）
4. `agent-service/app/trace/store.py`（`RunStore` 契约）
5. `infra` / `V001`–`V003` migrations（表名与约束）

## 0. 一句话结论

T032 交付的不是"节点连起来"，而是**一条可恢复、可审计、不可被模型越权的 State 演化通道**：

```text
LangGraph 负责 State 驱动执行（何时做）
T031      负责单次写的安全语义（如何安全做）
RunStore  负责当前 run 的唯一状态（谁能继续）
Java      负责业务事实（什么是真的）
```

---

## 1. T032 Runtime 总架构图

```text
┌──────────────────────────────────────────────────────────────────┐
│ Web / Flow Playground                                  【已存在】 │
└───────────────────────────────┬──────────────────────────────────┘
                                │ HTTP + Bearer JWT
┌───────────────────────────────▼──────────────────────────────────┐
│ Agent API   /runs /input /resume /events /trace        【已存在】 │
│   ★T032：/input、/resume 必须把执行【重新送回 Graph】             │
│          现状只写一行 checkpoint，并不解释文本、也不推进图         │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│ ★★★ T032 Agent Brain — State-driven Runtime                     │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│   │   Nodes      │    │   Router     │    │ State Transition │   │
│   │ 输入/输出=State│◀──│ LLM 提议     │──▶ │ advance() 校验   │   │
│   │ 无隐藏可变状态 │    │ Router 约束  │    │ transition() 生命周期│
│   └──────┬───────┘    └──────────────┘    └────────┬─────────┘   │
│          │                                          │            │
│          │      节点边界显式 checkpoint（不是自动）    │            │
└──────────┼──────────────────────────────────────────┼───────────┘
           │                                          │
           │      ┌───────────────────────────────────▼──────────┐
           │      │ RunStore（侧向轨道）                  【T017】│
           │      │   agent.agent_runs        状态/版本/预算      │
           │      │   agent.agent_checkpoints 全量 State 快照     │
           │      │   agent.tool_executions   结构化 Tool Trace   │
           │      └──────────────────────────────────────────────┘
           │ typed tools（allowlist + risk metadata）
┌──────────▼───────────────────────────────────────────────────────┐
│ Tool 层   CommerceTools / ToolRegistry                    【T029】 │
└───────────────────────────────┬──────────────────────────────────┘
                                │ HTTPS + Idempotency-Key
┌───────────────────────────────▼──────────────────────────────────┐
│ Java Business Authority   ownership / eligibility / 资金  【T019–028】│
└───────────────────────────────┬──────────────────────────────────┘
                                ▼
             PostgreSQL   commerce.* = 业务权威    agent.* = Agent 投影
```

1. LangGraph **不拥有业务事实**，也**不拥有最终状态**；它只负责 State 驱动执行。
2. RunStore 是**侧向轨道**：Tool 调用不经过它，只有节点边界**显式**写入。负责状态保存、checkpoint、trace、resume 依据。
3. Java 是业务事实的**唯一来源**；Agent 侧保存的是**业务事实的投影 + 恢复依据**。
4. `/input` 与 `/resume` 是恢复入口，必须重新进入 Graph，而不是只改一行状态。
5. `advance()` 是 T032 **唯一新增的** State 变更入口（一个校验构造函数，不是新架构概念）；其余名字全部沿用现有代码。

---

## 2. Graph 主流程图

```text
 START
   │
   ▼
 understand ── LLM 提议 ──▶ Router 约束
   │
   ▼
 resolve_order ── Java get_order（owner-scoped）──┐
   │                                              │ 候选不唯一 / 无法确认
   │                                              └──────▶ WAITING_USER
   │                                                          │ 用户补充
   │                                                          ▼ POST /input
   ▼                                                   重新进入 resolve_order
 evidence_router ◀──────────────────────────────────────────────┘
   │
   ├── 证据不足 ──▶ execute_evidence ──┐
   │                                   └──▶ 回 evidence_router
   ├── 证据足够 ──▶ check_eligibility ── Java EligibilityService
   │                    │
   │                    ├─ eligible 且 allowedAction 含退款 ──▶ refund_write
   │                    └─ 否则 ─────────────────────────────▶ finalize
   ▼
 refund_write ────────────────────────────────────▶ 见 §4
   │
   ▼
 verify ── 只读 get_after_sales_status(同一个 key)
   │
   ▼
 finalize ── transition()（不是 checkpoint_state）──▶ COMPLETED / SAFE_STOP / FAILED
```

0. `understand` 还有一条到 `WAITING_USER` 的边（图上未画出）：`intent` 缺失或为 `UNKNOWN` 时**不进入**
   订单解析——没有目标就无从判断哪个 capability 合适，猜一个等于替用户决定他要什么。
1. 每个节点只做两件事：`state = advance(state, **changes)` 与 `return {"state": state}`。
   **禁止 `model_copy(update=...)`**：实测它跳过校验，会让 `extra="forbid"`、预算守卫、凭据扫描在图里静默失效。
2. Graph 的 state schema 是 `GraphState = TypedDict`，分**载荷**与**控制面**两类通道：
   - 载荷：`state: AgentState` —— 权威事实，每次变更都经 `advance()` 重建校验；
   - 控制面：`decision: Decision`（当前节点提议 / guard 裁定 / 节点自述的 safe-stop 原因）、
     `understood: UnderstoodRequest | None`、`resolution: OrderResolution | None`。
   **控制面三通道一律不持久化**：它们是本次 invocation 的中间产物，`resume` 时重新推导。
   这是 T030 harness 的既有数据流（它把 `understood` / `resolution` 放在请求内局部变量里串起来），
   而把它们写进 `AgentState` 会让"模型的解释"和"Java 的事实"并排存放，后来的人就分不清了。
   durable 层的对应物是 run 行的 `current_node` / `next_action` / `version` 与 tool trace。
3. **Router 的输入是 `(AgentState, ToolRegistry risk metadata, stage guard)`**：LLM 生成候选动作，Router 决定合法下一节点。LLM 提议，Router 约束。
4. 预算两层：条件边上的守卫主拦（超限 → `safe_stop`）；`advance()` 内的 `validate_budgets` 兜底（命中即 `SAFE_STOP`，不是 500、也不是 `FAILED`）。
5. `verify = UNKNOWN` 时 finalize **不得**输出成功。
6. **证据路径的失败分类（节点记录事实，Router 决定流程）**：`execute_evidence` **不把失败写入
   `evidence[]`**（那里只装观察到的成功事实），失败只进 `tool_history`。它按
   `ToolEnvelope.retryable` + run 级 retry 预算，决定**重试**还是**关闭当前证据路径**
   （`Decision.evidence_path_closed`）——这是**关于这条路径的事实，不是路由决定**：节点既不知道
   也不选择下一步去哪，把"路径已关闭"映射成 `check_eligibility` 是 `route_after_decision` 的职责，
   所以拓扑要改时只改路由。三种结果（成功 / 瞬时失败重试 / 路径关闭）**都不终止整条 run**：
   少一条证据，资格结论仍归 Java。
7. **重试只有一个机制**：节点报 `Decision.retry_current_stage`（事实），由 Router 决定"这意不意味着
   重进本阶段"。`route_after_execute` 据此回到 `EXECUTE_EVIDENCE`（重试那次**已授权**的读取，而不是
   再问一次模型），`route_after_eligibility` 据此自环回 `CHECK_ELIGIBILITY`（它没有循环边，
   没有这个信号就会把"Java 答不出来"结束成 `COMPLETED`——那是个谎）。
8. **交接令牌由路由层产出**：`check_eligibility` 要求 guard 决策是 `ALLOWED + READY_FOR_ELIGIBILITY`，
   而通向它的三条路径里只有一条天然满足（模型说够了）。因此 `routing.eligibility_handoff(decision)`
   负责产出令牌，`HandoffReason` 把来源（模型说够了 / guard 拒绝 / 路径关闭）写进 `reason_code`。
   **判断与推导物的区别**：授权凭证（guard 对某次调用的裁定）不可重建——重建即伪造判断；
   交接令牌可以重建——它由事实确定性推导，携带的是来源而非许可。
9. **钱路径的顺序是硬约束**：`refund_write` 派生意图 → 交给 T031 的 `persist_intent` 回调**先落盘**
   → 才允许发出唯一一次请求；`persist_intent` 失败则一个字节都不发，落 `SAFE_STOP`
   （reason `WRITE_INTENT_NOT_DURABLE`：**"我们正确地没做"**）。写节点**不做任何重试**：
   `RefundWriteOutcome` 报告 T031 已消耗的 `attempts` 且**没有** `retryable` 字段，因为写的重试
   不是一次动作而是一套程序（未知 → 读权威 → 同 key → 预算耗尽落 UNKNOWN），这套程序只有一个所有者。
10. **验证以"有持久 intent"为前提**：`verify` 按幂等 key 读权威，所以 `route_after_write` 只在
    `write_intent is not None` 时才去 `VERIFY`——无 intent 意味着**从未发出**（T022），
    既没有问题要问，也没有 key 可问。

---

## 3. 双轨 State 演化图

恢复必须同时拿到 **Payload** 与 **Position**，缺一不可。

```text
    数据轨：AgentState（agent.agent_checkpoints.state_json）
    ────────────────────────────────────────────────────────────
 START        user_request
   │
 understand   + intent、candidate_order_ids
   │
 resolve_order+ resolved_order_id        （Java owner-scoped 确认后才写）
   │
 evidence_*   + evidence[]               （只收成功的 Tool 响应）
   │
 eligibility  + eligibility              （Java 决策的副本）
   │
 refund_write + write_intent、write
   │
 verify       + verification             （观察 Java 事实）
   │
 finalize     + status（经 transition）

    控制轨：agent.agent_runs（行投影）
    ────────────────────────────────────────────────────────────
 status（RUNNING / WAITING_USER / …）
 current_node
 next_action
 step_count / retry_count
 version            ← CAS 的并发令牌
 intent / resolved_order_id   ← 行投影，便于查询与运维排查
```

1. 数据轨给"事实是什么"，控制轨给"从哪继续"；`resume` 靠的是后者 + `version`。
2. 控制轨不是冗余：`current_node` / `next_action` 决定重入点，`version` 决定并发恢复的唯一赢家。
3. 两轨在同一次 `checkpoint_state` 里一起写：行值与其 `state_json` 来自同一个 dict、同一条 UPDATE，因此不可漂移。
4. `WAITING_USER` 是**状态迁移 + 图退出**，不是一个节点：`/input` 把文本并入 `user_request`，再把执行送回图。
5. 边界条件：`user_request` 上限 4000 字符，追加澄清文本必须显式处理超限，不能静默截断。

---

## 4. refund_write 状态机

持久化状态只用真实的 `WriteStatus` 五个值。**不新增枚举**。

```text
 advance(step_count+1)
        │
        ▼
 ┌───────────────────────────┐
 │ INTENT_PERSIST            │  checkpoint_state(write_intent, expected_version=V)
 │   idempotency_key = K     │  write.status = PENDING
 │   request_fingerprint = F │
 │   target_id = order_id    │
 └──────────┬────────────────┘
            ├── 落盘失败 ──▶ 一个字节都不发 ──▶ write.status 保持 NOT_ATTEMPTED ──▶ SAFE_STOP
            ▼
 ┌───────────────────────────┐
 │ REQUEST_SENT              │  POST /api/v1/refunds   (Idempotency-Key: K)  ← 只发一次
 └──────────┬────────────────┘
            │
   ┌────────┴─────────┬──────────────────────┐
   ▼                  ▼                      ▼
 2xx 成功         权威拒绝              结果未知（timeout / 契约外 5xx）
 SUCCEEDED        FAILED                        UNKNOWN
                  (终态)                          │
                                                  ▼
                                     ┌─────────────────────────┐
                                     │ READ_AUTHORITY          │ get_after_sales_status(K)
                                     └────────┬────────────────┘
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                        查到这笔 K                     查不到这笔 K
                        SUCCEEDED                      ├─ 预算未超 & fingerprint 一致 ──▶ 同 K 重发
                        （来源 = authority readback）   └─ 否则 ──▶ UNKNOWN / SAFE_STOP
                        fingerprint 漂移 ──▶ fail closed ──▶ SAFE_STOP
                              │
                              ▼
        checkpoint_state(write_outcome, expected_version=V+1)
```

1. 恢复成功**不是新状态**：`UNKNOWN → verify → Java 已成功 → SUCCEEDED`。来源通过 `agent.tool_executions` 追踪，不污染业务状态枚举。
2. `PENDING` = 意图已落盘、请求已发或即将发出，是崩溃恢复**唯一的锚点**；`WriteIntent` 的存在正是为了区分"从未发出"与"发了但未知"。
3. **崩溃窗口 A**（intent 在盘、请求未发）与**窗口 B**（Java 已提交、结果未知）恢复时必须可区分：A 可正常开始，B 禁止重发、先读权威。
4. 重试只允许在"权威确认不存在"之后发生，且**必须复用同一个 K**；`request_fingerprint`（64 位小写 hex SHA-256）不一致一律 fail closed。
5. 两次落盘都带 `expected_version`。**绝不能把 `UNKNOWN` 直接变成 `SUCCEEDED`。**

---

## 5. T031 / T032 / T017 边界图

```text
┌───────────────────────────────────────────────────────────────┐
│ T032 —— 什么时候做                                             │
│   Graph 编排 · Node 调度 · Router · State Transition           │
│   checkpoint 时机与顺序 · step / retry budget                  │
└───────────────────────────┬───────────────────────────────────┘
                            │ 调用（注入 tools + store + state）
                            ▼
┌───────────────────────────────────────────────────────────────┐
│ T031 —— 如何安全做                                             │
│   execute_write：write-ahead intent · 单次尝试                 │
│                  unknown → authority readback · same key retry │
│                  预算耗尽 → UNKNOWN · intent 落盘失败则不发     │
│   verify_business_state：按同一 key 读 Java 权威，自己不重试    │
└───────────────────────────┬───────────────────────────────────┘
                            │ 持久化与并发仲裁
                            ▼
┌───────────────────────────────────────────────────────────────┐
│ T017 RunStore —— 当前 run 的唯一状态                            │
│   agent_runs · agent_checkpoints · agent.tool_executions       │
│   row lock + expected_version CAS                              │
└───────────────────────────────────────────────────────────────┘
```

1. T032 决定**什么时候做**；T031 决定**如何安全做**；RunStore 决定**当前 run 的唯一状态**。
2. **反向约束**：T032 不得自行判断"这笔退款成功了没有"（verify 的职责）；T031 不得决定"这个 run 该不该结束"（Router / `transition()` 的职责）。
3. RunStore 不属于任何一方，它是三方共用的仲裁层——"run 现在是什么状态"永远只有一个答案。
4. 这个边界就是选"自管持久化、`compile(checkpointer=None)`"的原因：引入框架自带 checkpointer 会产生第二份状态真相。

---

## 6. Node Contract 表

| Node | 输入（读） | 输出（写） | 唯一允许改动的 State 字段 | 落盘时机 |
|---|---|---|---|---|
| `understand` | `user_request` | `intent`、`candidate_order_ids` | `intent`、`candidate_order_ids` | 出节点后 `checkpoint_state` |
| `resolve_order` | `candidate_order_ids`、`intent` | `resolved_order_id` 或 `WAITING_USER` | `resolved_order_id` | 出节点后 `checkpoint_state`；`WAITING_USER` 走 `transition()` |
| `evidence_router`（`decide_next_evidence` + `guard_evidence_proposal`） | `evidence[]`、`resolved_order_id`、`tool_history` | 路由决策 → `next_action` | **不写业务字段**（只写控制轨 `next_action` + trace） | 决策记入 trace |
| `execute_evidence`（`execute_read_evidence`） | `resolved_order_id` | `evidence[]`、`tool_history` | `evidence`、`tool_history` | 出节点后 `checkpoint_state` |
| `check_eligibility`（`check_eligibility`） | `resolved_order_id` | `eligibility` | `eligibility` | 出节点后 `checkpoint_state` |
| `refund_write`（`refund_write_intent` + `execute_refund_write`） | `eligibility`、`resolved_order_id` | `write_intent`、`write` | `write_intent`、`write` | **节点内两次**：先 intent、后 outcome，均带 `expected_version` |
| `verify`（`verify_refund_business_state`） | `write_intent`、`write` | `verification` | `verification` | 出节点后 `checkpoint_state` |
| `finalize` | 全部已核实事实 | `status`（终态） | `status` | `transition()`（**不是** `checkpoint_state`） |
| `safe_stop` | 停止原因 | `status = SAFE_STOP` + reason code | `status` | `transition()` + trace 记 reason code |

1. 表里的函数名全部是当前代码里已存在的实现；`evidence_router` 与 `refund_write` 是**组合节点**（一个节点内调用多个已有函数），不是新概念。
2. "唯一允许改动的 State 字段"是硬约束：一个节点改了别的字段，就是越权，应由测试拦住。
3. `evidence_router` 刻意不写业务字段——它只决定"下一步取什么证据"，裁定结果进 trace，保持业务 State 的可信度。
4. `checkpoint_state` **不允许改 `status`**；生命周期变更只能走 `transition()`。两者分工固定：事实落盘 vs 状态迁移。

---

## 7. State 字段可信度表

| State 字段 | 来源 | 模型是否可修改 | 失败方式 |
|---|---|---|---|
| `principal` | Java `GET /me` | 否 | 构造失败（`AuthContext` 不含身份，写不出来） |
| `resolved_order_id` | Java owner-scoped `get_order` | 否 | 未确认不允许写入；候选留在 `candidate_order_ids` |
| `evidence[]` | 成功的 Tool response | 否（只能提议取何种证据） | 非成功响应直接丢弃 |
| `eligibility` | Java `EligibilityService` | 否 | 只复制，不计算 |
| `write_intent` / `write` | T031 状态机 | 否 | Tool 参数对模型不可见 |
| `verification` | Java after-sales 权威 | 否 | 读失败只能是 `UNKNOWN` |
| `intent` | LLM（schema 约束） | **是** | 自由文本，**永不参与授权** |
| `status` / `step_count` | Router + `transition()` | 否 | `checkpoint_state` 拒绝修改 `status` |
| `approval` | Java 审批记录（US5/T049） | 否 | 当前只记录主张，不作为授权 |

1. 判据：**写不出这三行的字段，就不该进 `AgentState`。**
2. 不增加布尔字段描述已被事实蕴含的信息（例如不写 `ownership_verified`，`resolved_order_id` 存在即表示 Java 已完成 owner-scoped 确认）。
3. 唯一允许模型影响的是 `intent`，且它不参与任何授权判定。
4. 所有"来自 Java"的字段都只经**唯一的服务入口**写入，模型输出永远先进 proposal，再由 guard 裁定。

---

## 8. 命名纪律（禁止清单）

以后修改本设计或实现时，以下名字**一律禁止出现**：

```text
禁止的表名        trace_events            → 用 agent.tool_executions
禁止的 WriteStatus WRITE_RECOVERED        → 用 SUCCEEDED（来源记 trace）
禁止的 WriteStatus VERIFY_REQUIRED        → 用 UNKNOWN + verification 状态
禁止的 WriteStatus WRITE_INTENT_CREATED   → 用 PENDING
禁止的字段         ownership_verified      → 用 resolved_order_id 是否存在
禁止的字段         evidence_status         → 用 evidence[] / 控制轨 next_action
禁止的字段         business_fact           → 用 verification: VerificationOutcome
```

理由：业务状态枚举一旦被"过程状态"污染，恢复逻辑与 Eval 口径都会失去唯一的判据；已被事实蕴含的信息做成字段，只会引入一个会和事实漂移的第二真相。

---

## 9. 待决项（记录下来，不在 T032 解决）

1. **HITL 与 `interrupt()`**：本设计选 `compile(checkpointer=None)`，因此没有框架原生 `interrupt()`。US5/T049 需要在两条路里选：自管 resume（已有 `RunStore.resume` + CAS 赢家），或引入 LangGraph checkpointer 但降级为"图内记忆"、run 状态仍以 RunStore 为准。
2. **`langgraph-checkpoint-postgres` 当前声明但未使用**：保留（T049 可能用到），但必须在 `PROJECT_PROGRESS.md` 写明"当前未使用"，避免被误读为持久化路径。
3. **`/input` 文本并入 `user_request` 的超限策略**：`user_request` 上限 4000 字符，追加澄清需要显式规则（拒绝并提示，或按策略重写），不允许静默截断。
4. **`advance()` 的归属**：作为 `AgentState` 上的唯一变更入口；配套 meta-test 断言 `app/agent/` 下不出现 `model_copy(update=`。
   **状态更新（已落地）**：`advance()` 已实现，meta-test 采用**显式白名单 + 双向断言**（新增一处失败、白名单过期也失败）；
   白名单里剩下的两处是 `dev_t031.py`（dev harness）与 `checkpoint.py`（读路径把行上的 5 个共享列盖回 payload，
   行是更新的事实）。**写路径那一处已修**：`store.transition()` 原先用 `model_copy` 重建 payload、只跑凭据守卫，
   会让 `step_count` 绕过 `validate_budgets`；现在改用 `advance()` 重建，并有真库用例证明被拒的写没有留下任何东西。
5. **`check_eligibility` 把"阶段令牌"当成了"授权凭证"**：它要求 `EvidenceGuardDecision` 为
   `ALLOWED + READY_FOR_ELIGIBILITY`，而"证据阶段结束"其实有三个来源（模型说够了 / guard 拒绝取证 /
   读取失败路径关闭）。本设计用路由层的 `eligibility_handoff()` 满足这个前置条件（决定 D），
   **假耦合仍在**。真正的修法是让 `check_eligibility` 接受"阶段已结束"这个事实而不是一个授权凭证——
   但它属于 T030 已验收代码，且作者刻意写了 3 个前置条件用例，因此留到将来真正需要时一并处理。
6. **`Decision` 上的三个控制面事实**（`guard` 原对象、`evidence_path_closed`、`retry_current_stage`）都只活在
   一次 invocation 内，`resume` 时重新推导；durable 的对应物仍是 run 行的 `next_action` / `version` 与 tool trace。
7. **环境（非代码）**：本机工作区曾被 Windows 文件权限挡住（缺少"取得所有权"），已用 DSH 的文件权限诊断脚本
   修复并验证；但 `.ruff_cache` / `.mypy_cache` / `.pytest_cache` 仍拒绝写入，因此门禁用等价命令：
   `ruff check --no-cache`、`ruff format --check --no-cache`、`mypy app --cache-dir=<TEMP>`、
   `pytest -q -p no:cacheprovider`。另外受限模式下 `git fetch` / `git commit` 写不进 `.git`，需要一次完全权限。
