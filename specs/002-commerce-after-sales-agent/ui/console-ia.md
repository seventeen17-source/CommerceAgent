# UI-1.1 Console IA 冻结（T104）

2026-10-13。本文定义 CommerceAgent Web 的**产品命名、入口、导航、路由、页面映射、API 映射与 UX contract**，是前端体验层的 IA 权威。

权威顺序（冲突时前者优先）：`data-contract.md`（字段与权限）→ `acceptance.md`（场景与验收）→ `design-system.md`（视觉与组件）→ `pages.md`（逐页 UX）→ 本文（命名与路由）。**本文只改命名与导航，不改任何安全约束、字段来源或验收口径。**

产品定位：**两个入口、一个 Web 应用**。

| 入口 | 路由根 | 负责 | 不做 |
|---|---|---|---|
| **Customer Portal** | `#/portal` | 客户提交售后请求、澄清、查看结果 | 不暴露内部技术语言，不进入企业导航 |
| **Enterprise Agent Console** | `#/console` | 展示 Agent Runtime 的判断、证据、边界、核验与恢复 | 不代客户发起资金动作 |

叙述结构固定为 `User Request → Evidence → Decision → Controlled Action → Verification`；界面必须解释「Agent 为什么这么做」，而不只展示「发生了什么」。**不设计成 AI 客服系统，也不设计成传统售后后台。**

---

## 1. 最终导航

**Enterprise Agent Console 主导航（6 项，固定顺序，均挂在 `#/console` 下）**

| 顺序 | 导航名 | 规格页 | 角色 |
|---|---|---|---|
| 1 | Mission Center | P01 Dashboard | 企业 |
| 2 | **Run Replay**（核心入口） | P03 Workspace | 企业 |
| 3 | Case Context | P04 Case Detail | 企业（受权） |
| 4 | Human Collaboration | P05 Approval Center | APPROVER |
| 5 | **Safety Center**（核心） | P06 Recovery Center | 企业 |
| 6 | Enterprise Dashboard | P07 Analytics | 企业 |

**独立入口（不进入 Console 导航）**

- **Customer Portal**（P02）：`#/portal`。它是**发起入口**，不是后台。保留原因是权限事实：`POST /agent/runs` 需要客户身份且 Run 是 owner-scoped，APPROVER 读不到客户 Run（`data-contract.md:19`）。删掉它，浏览器就发不出真实 Run。
- **Flow Playground**：`#/dev/playground`，仅开发环境可见，保留 T016 起的既有验收能力。

**入口形态决定**：采用**同一 Web 应用的两个独立子路径**（`#/portal` 与 `#/console`），**不做登录页身份切换、不做独立子域**。理由：Demo 需要“客户提交 → Agent 处理 → 企业查看”的清晰叙事；子域会引入 DNS、多部署、CORS 与登录同步成本，当前阶段不需要。

**侧栏底部**：当前身份（角色 / userId 来源）、退出登录、版本与数据范围说明。
**顶栏右侧**：系统健康（仅真实探测结果，否则“状态未获取”）、当前数据范围与 `asOf`、Demo 标识（Demo 场景常驻）。

---

## 2. 路由设计

Hash 路由。**路由只存 ID 与筛选**，不放 token、请求原文、授权金额、幂等键（`design-system.md:45`）。

**Customer Portal**

| 路由 | 页面 | 参数与行为 |
|---|---|---|
| `#/portal` | P02 发起售后 | 提交态：左表单右“处理方式”简述；提交后左只读请求摘要、右真实进度 |
| `#/portal/runs` | P02 我的任务 | 依赖 owner Run 列表（T098）；缺失时显示可解释空态 |
| `#/portal/runs/:runId` | P02 处理进度与结果 | 澄清、等待审批、已核验结论、终态文案 |

**Enterprise Agent Console**

| 路由 | 页面 | 参数与行为 |
|---|---|---|
| `#/console` | 分发 | 默认进入 `#/console/mission` |
| `#/console/mission` | P01 Mission Center | `?range=today\|7d\|30d&status=…`；游标不写入 URL，返回恢复滚动 |
| `#/console/runs/:runId` | **P03 Run Replay** | `?node=:id`；默认选中：未越界路径=Verification，越界路径=当前等待节点 |
| `#/console/cases/:runId` | P04 Case Context | `?section=evidence\|result`；对象不一致以服务端为准 |
| `#/console/collaboration` | P05 Human Collaboration | `?approvalId=:id`；无参时列表默认 `PENDING` |
| `#/console/safety` | P06 Safety Center | `?runId=:id&kind=failure\|recovery\|unknown` |
| `#/console/enterprise` | P07 Enterprise Dashboard | `?range=…&metric=…`；样本钻取回 `#/console/runs/:runId` |
| `#/dev/playground` | Flow Playground | 仅开发环境 |
| `#/` | 入口分发 | 客户身份 → `#/portal`；企业/审批身份 → `#/console/mission` |

**通用行为**：深链接先认证再授权读取；返回列表恢复筛选与滚动；切换身份立即清空 Run/订单/消息与缓存，旧响应按 identity generation 丢弃；`COMPLETED` 不等于写入成功，页面不得据此推导结论。

---

## 3. 页面映射（与旧编号、参考图、后端依赖）

| 规格页 | Console 命名 | 参考图 | 原任务号 | 主要后端依赖 |
|---|---|---|---|---|
| P01 | Mission Center | `dashboard.png`（按语义修订） | T099 | T098（列表/指标） |
| P02 | Customer Portal（独立入口） | `customer.png`（删 58% 与草稿按钮） | T087–T091 | 已发布接口为主；列表需 T098 |
| P03 | **Run Replay**（核心） | `workspace.png`（结构冻结） | T092 | T085/T086（字段投影）、T092（详情摘要） |
| P04 | Case Context | 无（首张截图建立基准） | T100 | T097/T098（case context、工单读取） |
| P05 | Human Collaboration | 无（同上） | T091 + 既有 ApprovalCenter | 已发布 approvals 三条 |
| P06 | **Safety Center**（核心） | 无（同上） | T101 | T085、T092、工单读取 |
| P07 | Enterprise Dashboard | 无（同上） | T102 | T093、T098（metrics） |

逐页视觉基准与组件复用归 T103；跨页面视觉与可访问性收口归 T094；跨服务 Live Gate 归 T095。
`pages.md` 章节标题保留 P0x 编号，产品命名一律以本表为准。

---

## 4. 任务执行顺序（2026-10-13 裁决）

```
T104 Console IA Freeze（本文）
  ↓
T106 Run Replay ⭐（提前）
  ↓
T105 Mission Center
  ↓
T107 Case Context
  ↓
T108 Human Collaboration
  ↓
T109 Safety Center
```

**为什么 Run Replay 先于 Mission Center**：① 它是本产品唯一的差异化展示面——LangGraph Runtime、状态迁移、证据驱动决策、Tool Calling、HITL、Verification，都是普通 AI 客服与传统售后系统做不出来的；② 今天就有真实 Run 数据可支撑（`order-001` ¥199 自主完成 / `order-004` ¥399 越界暂停）；③ Mission Center 是聚合层，若 Run 体验的数据模型没冻结，它会先变成空壳 Dashboard。**先建 Run Experience，再做 Metrics。**

---

## 5. API mapping

标记：✅ 已发布且已实现 ｜ ⚠️ 已发布但字段不足 ｜ ❌ 缺（登记任务，不虚构）

### 5.1 通用 / 身份

| 用途 | 端点 | 现状 |
|---|---|---|
| 当前身份与角色 | Java `GET /api/v1/me` | ✅ |
| 登录（客户 / 审批员） | Java `POST /api/v1/auth/login` | ⚠️ 仅存在于未提交代码（T096），未验收；退路 `scripts/mint_dev_token.py` |
| 系统健康 | Agent `GET /health`；Java actuator | ✅ |

### 5.2 Mission Center（P01）

| 用途 | 端点 | 现状 |
|---|---|---|
| 近期 Run 列表（跨 owner，受权） | Agent `GET /api/v1/agent/operations/runs` | ❌ T098 |
| 指标 N/T/V/A/H/R/S 与失败分组 | Agent `GET /api/v1/agent/operations/metrics` | ❌ T098 |
| Attention Required（暂停原因、审批/工单引用） | 同上列表的 `needsAttention` | ❌ T098 |
| 兜底（T098 之前） | Agent `GET /api/v1/agent/runs/{runId}` + 深链 | ✅（仅 owner；不含跨 Run 汇总） |

### 5.3 Run Replay（P03，核心）

| 用途 | 端点 / 字段 | 现状 |
|---|---|---|
| Run 头部：状态、步数、核验、终态文案 | `GET /agent/runs/{runId}` → `status/stepCount/verificationStatus/verifiedRefundRequestId/finalMessage/errorCode/version` | ✅ |
| 澄清等待（候选订单） | 同上 → `clarification.kind/candidateOrderIds` | ✅ |
| **边界账**（越界/未越界、规则码、阈值、可退金额） | `eligibility.ruleCode/ruleVersion/maxRefundAmount/approvalRequired/reasonCodes` + `approval_threshold` | ❌ T086；阈值未发布 → 第一版只写“业务规则要求人工审批” |
| **判断轨**：7 组事件、工具、错误码、耗时、摘要 | `GET /agent/runs/{runId}/trace` → `node/toolName/status/errorCode/latencyMs/summary/timestamp` | ⚠️ 基础可用；输入/输出详细摘要 ❌ T092 |
| **未知账**：是否发出过请求 × 结果是否已知 | `write_intent` 存在性 + `write.status` + `verification.status` + `stopReason` | ❌ T085/T086 |
| 证据面板（Evidence：事实/来源/观测时间/历史或当前） | T086 白名单投影 | ❌ T086 |
| 规则与决策（Rule / Decision，Agent 提议与 Java 结论分开） | T086 | ❌ T086 |
| 底部 Verification（确认强度：读回核验 vs 写响应确认） | `verificationStatus` + confirmation 类型 | ⚠️ 状态 ✅；确认强度 ❌ T085 |
| 左栏队列（Run 列表） | 同 5.2 列表；T098 之前用单 Run 深链 + 本地最近访问 | ❌ T098 |
| 订单与物流事实 | Java `GET /orders/{orderId}`、`GET /orders/{orderId}/logistics` | ✅ |

### 5.4 Case Context（P04）

| 用途 | 端点 | 现状 |
|---|---|---|
| 本人订单摘要/详情 | Java `GET /orders`、`GET /orders/{orderId}` | ✅ |
| 物流快照 | Java `GET /orders/{orderId}/logistics` | ✅ |
| 售后状态（退款/退货） | Java `GET /orders/{orderId}/after-sales` | ✅ |
| 工单上下文 | Java `GET /api/v1/support-tickets/{id}`（后续 `/timeline`、`/evidence`） | ❌ **归入 T098**（Support Ticket Context API），不单列任务 |
| Run ↔ 业务对象绑定投影（运营视角） | Agent `GET /api/v1/cases/{runId}` / `GET /api/v1/operations/cases/{runId}` | ❌ T097/T098 |

### 5.5 Human Collaboration（P05）

| 用途 | 端点 | 现状 |
|---|---|---|
| 待办/已办列表 | Java `GET /api/v1/approvals?status=…` | ✅ |
| 审批详情（绑定 run/order/action/amount/ruleCode/expiresAt） | Java `GET /api/v1/approvals/{approvalId}` | ✅ |
| 批准/拒绝 | Java `POST /api/v1/approvals/{approvalId}/decision` | ✅ |
| 绑定对象证据上下文 | Agent/Java `GET /operations/approvals/{id}/context` | ❌ T097/T098 |
| 客户同 Run 继续执行 | Agent `POST /agent/runs/{runId}/resume` | ✅（客户身份；审批台不代客户发起） |

### 5.6 Safety Center（P06）

| 用途 | 端点 | 现状 |
|---|---|---|
| 失败/恢复/未知列表 | `GET /api/v1/agent/operations/runs?kind=…` | ❌ T098 |
| 终态停止原因 `stopReason` | T085 投影 | ❌ T085 |
| 结构化恢复序列（超时→未知→读权威→找到/重试/停止） | trace + 恢复证据 | ⚠️ trace 基础 ✅；重试次数与是否同逻辑请求 ❌ T092 |
| 工单摘要 | Java `GET /api/v1/support-tickets/{id}` | ❌ 归 T098（当前只有 `POST`） |
| 未知写入边界（不得标零写） | `write.status` / `write_intent` 存在性 | ❌ T086 |

### 5.7 Enterprise Dashboard（P07）

| 用途 | 端点 | 现状 |
|---|---|---|
| 四指标 + 失败类型 + 样本钻取 | `GET /api/v1/agent/operations/metrics` | ❌ T098 |
| 离线 Eval 报告证据（与运行统计分开标数据集） | T093 报告投影 | ❌ T093 |

### 5.8 Customer Portal（P02，独立入口）

| 用途 | 端点 | 现状 |
|---|---|---|
| 提交售后 | Agent `POST /agent/runs`（body 只有 `message`） | ✅ |
| 本人订单/详情/物流 | Java `GET /orders`、`/orders/{orderId}`、`/orders/{orderId}/logistics` | ✅ |
| 澄清继续 | Agent `POST /agent/runs/{runId}/input` | ✅ |
| 进度与结果 | Agent `GET /agent/runs/{runId}` | ⚠️ 缺 stopReason、工单号 |
| 等待审批查询（本人） | Java `GET /approvals/{id}` | ✅ |
| 审批后继续 | Agent `POST /agent/runs/{runId}/resume` | ✅ |
| 我的任务列表 | Agent `GET /api/v1/agent/runs`（owner 列表） | ❌ T098 |

---

## 6. 数据可得性分级（决定每个 Task 当天能做出多少）

| 级别 | 含义 | 覆盖的 Console 面 |
|---|---|---|
| **A. 今天可用** | 已发布接口即可渲染真实数据 | Run Replay 头部 / 判断轨 / 底部核验；Case Context 订单与物流；Human Collaboration 全流程；Customer Portal 除列表外全部 |
| **B. 需 T085/T086** | 已建能力但字段未投影 | 边界账数值、证据面板、规则与决策、未知账、确认强度 |
| **C. 需 T097/T098** | 运营只读面尚未存在 | Mission Center 列表与指标、Safety Center 列表、Enterprise Dashboard、Case/Approval context、工单读取、owner Run 列表 |

T106 被排在 T105 之前，正是因为它是唯一**当天就能产出 A 级真实内容**的核心页。

---

## 7. UX contract（所有页面共享，逐页规格仍需服从）

1. **状态语言**（原始枚举可对企业侧同时展示）
   `RUNNING` 处理中 ｜ `WAITING_USER` 等待你补充 ｜ `WAITING_APPROVAL` 等待人工审核 ｜ `COMPLETED` 执行已结束 ｜ `ESCALATED` 已转人工 ｜ `SAFE_STOP` 因安全边界停止 ｜ `FAILED` 执行失败。
   状态**始终带图标与文字**，不靠颜色单独表达；未知枚举降级为 UNKNOWN 并保留诊断码。
2. **共享组件**（唯一来源，禁止每页各写一份）
   `StatusBadge`、`RunCard`、`Timeline`、`EvidencePanel`、`SafetyEventCard`、`MetricCard`。
3. **三个判断对象**（Console 的差异化能力，必须由真实字段驱动）
   **边界账**（规则码/版本、可退金额、阈值、未越界→直接执行 或 越界→已暂停）；**判断轨**（已发生的事实与工具，未走过的节点标“不适用/未执行”）；**未知账**（是否发出过请求 × 结果是否已知，未知不得写成失败或零写入）。
4. **呈现约束**：每个智能元素背后必须有已存在且可追溯的字段；无字段就登记任务，不画、不动效、不造假进度（`design-system.md`「呈现约束」）。
5. **数据缺失**：无来源写“未获取/待确认”，保留区域与尺寸；禁止填示例值；Demo 数字必须带 Demo 标识，Live 无样本用“— / 无样本”。
6. **权限**：owner-scoped 读取；APPROVER 不自动获得客户 Run/订单/物流读取权；界面适配器只从已发布字段读，不透传原始 payload、JWT 或幂等键。
7. **写入纪律**：写未知不自动重试、不乐观更新；读请求可重试；弹窗外关闭不能取消已发出的写请求。
8. **响应式**：基准 1600×1000；1440 / 1280 / 390×844 三档；<1024 导航折叠，Run Replay 三栏转抽屉；不为塞进一屏而缩小正文。
9. **可访问性**：焦点环可见、字段错误关联、结果用 polite live region、正文对比度 4.5:1。
10. **禁用清单**：模拟运行/假进度百分比、“自动审批 / AI 自动批准”表述、机器人头像与 emoji 混排、为显得智能而添加的动画、原始 JSON 作为默认详情。

---

## 8. 与既有编号、归档的关系

- T104–T109 为本次前端体验层的**续号**（T103 是既有最后一个编号），不覆盖、不重排既有 T084–T103；执行顺序见第 4 节。
- 命名替换只发生在文档与界面文案层面：T099→Mission Center、T092→Run Replay、T100→Case Context、T091→Human Collaboration、T101→Safety Center、T102→Enterprise Dashboard；T087–T090 仍属 Customer Portal；T103/T094/T095 的验收范围不变。
- `specs/003` 的 UX001–UX052 与 `.specify/templates/ui/DESIGN.md` 仅作为视觉方向参考（Linear / Vercel / Agent observability 风格；Sidebar + Header + Workspace 布局），**不作为路线图与验收依据**；其建议的 Ant Design / React Flow / ECharts **本轮不引入**。
- **完整归档清单**（UX 线、旧 T084 正文、`feat/frontend-product-ui`、未提交的并行外壳、分支名处置）见 [README.md](README.md) 的「已弃用与归档」一节；遇到 UX 编号不要开工。

## 9. T104 自检

- [x] 两个入口（`#/portal` / `#/console`）与六个 Console 导航项均有规格页归属
- [x] 每条路由只承载 ID/筛选，无敏感数据
- [x] 每个页面可见值都能指到已发布接口或明确登记的任务
- [x] API 缺口全部登记（T085/T086/T092/T093/T097/T098 + 工单归 T098）
- [x] 未扩大任何权限，未虚构任何端点
- [x] 命名替换未改变 `data-contract.md` 与 `acceptance.md` 的任何约束
- [x] 任务顺序已按裁决更新（T104 → T106 → T105 → T107 → T108 → T109）

**已裁决**：① 顺序 = T106 Run Replay 提前（理由见第 4 节）；② 工单读取归 T098（Support Ticket Context API）；③ 入口形态 = 同应用双子路径 `#/portal` + `#/console`，不做身份切换与子域。
