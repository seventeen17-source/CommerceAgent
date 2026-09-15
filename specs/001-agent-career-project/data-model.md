# Data Model: 求职导向的 Agent 项目决策与设计

本数据模型描述研究与决策产物，不代表最终 Agent 应用的数据库设计。字段可以落在 Markdown 表格、CSV 或其他便于复核的结构化载体中。

## 1. Job Posting Sample

一条独立、可追溯、去重后的岗位证据。

| Field | Required | Description / Validation |
|---|---:|---|
| `job_id` | 是 | 稳定内部标识，不因展示顺序变化 |
| `title_raw` | 是 | 来源页面原始岗位标题 |
| `role_family` | 是 | Agent 应用、LLM 应用、AI 后端、AI 全栈、智能体工程或排除类 |
| `company` | 是 | 招聘主体；匿名来源须标注不可验证 |
| `company_type` | 是 | 大厂、AI 创业公司、传统企业数字化、企业软件/云服务等 |
| `location` | 是 | 城市/地区；远程单列 |
| `career_level` | 是 | 实习、校招、初级社招、高级趋势样本 |
| `published_or_observed_at` | 是 | 发布日期优先；无法获得时记录访问日期 |
| `source_url` | 是 | 可访问的直接页面，搜索结果页只能作线索 |
| `source_tier` | 是 | A 企业官方；B 权威招聘平台；C 聚合/转载，仅辅助 |
| `responsibilities` | 是 | 与应用工程有关的职责摘要 |
| `must_have` | 是 | 明确硬性要求，不把偏好项混入 |
| `preferred` | 是 | 加分或优先能力 |
| `exclusion_reason` | 否 | 若排除，说明纯算法/训练/资深/重复/失效等原因 |
| `dedupe_key` | 是 | 公司 + 标准化标题 + 地区 + 核心职责摘要 |
| `evidence_notes` | 是 | 页面限制、不确定字段与抽取判断 |

### Validation

- 核心样本必须为来源等级 A 或 B。
- 相同 `dedupe_key` 只保留一条主记录，转载链接作为别名保存。
- 高级趋势样本不得计入校招/初级样本占比。
- 仅包含模型训练、CUDA、RLHF 或论文研究职责的岗位标记为排除。

## 2. Capability Signal

对多个岗位样本中的一类能力需求进行语境化归纳。

| Field | Required | Description / Validation |
|---|---:|---|
| `capability_id` | 是 | 稳定标识 |
| `name` | 是 | 能力名称；框架名与底层能力分开 |
| `category` | 是 | 编程、后端、Agent、检索、评估、可靠性、安全、部署、前端等 |
| `evidence_job_ids` | 是 | 支持该信号的去重岗位集合 |
| `must_count` | 是 | 作为硬性要求出现的样本数 |
| `preferred_count` | 是 | 作为加分项出现的样本数 |
| `responsibility_count` | 是 | 在职责中实际使用的样本数 |
| `role_distribution` | 是 | 各岗位族的分布 |
| `context_summary` | 是 | 企业让候选人用它解决什么问题 |
| `confidence` | 是 | 高/中/低，按来源质量、样本数和跨公司一致性判定 |
| `learning_priority` | 是 | 两个月内核心、了解、暂缓 |
| `caveat` | 否 | 高频但不必用于本项目、术语歧义或样本偏差 |

## 3. Project Candidate

| Field | Required | Description / Validation |
|---|---:|---|
| `candidate_id` | 是 | 稳定标识 |
| `name` | 是 | 企业可理解的项目名 |
| `business_problem` | 是 | 明确痛点、损失或工作阻塞 |
| `target_users` | 是 | 日常使用者与审批者 |
| `business_system` | 是 | 将连接的业务数据与确定性业务逻辑 |
| `agent_necessity` | 是 | 说明不确定判断、多步任务和动态工具选择为何必要 |
| `not_just_chat` | 是 | 可观察的真实动作与状态变化 |
| `core_vertical_slice` | 是 | User → Agent → Tool → Business System → Result |
| `evaluation_feasibility` | 是 | 是否能构造可判定任务与失败样本 |
| `eight_week_scope` | 是 | 核心、延期和删除范围 |
| `fatal_risks` | 是 | 无数据、无真实动作、难评估、范围过大等 |
| `role_mapping` | 是 | 匹配公司与岗位族 |
| `scores` | 是 | 六维中心分、1～10 分锚点理由和证据等级 |
| `score_ranges` | 是 | 六维可辩护的低/中/高区间 |
| `weighted_total` | 是 | 按固定权重重算的低/中/高结果，范围 1.0～10.0 |
| `uncertainty` | 是 | 证据不足项、改变排序的条件与 4～8 小时验证方案 |

### Candidate State

`PROPOSED → SCORED → GATE_PASSED → RED_TEAMED → SELECTED`

- 未过致命门槛：`SCORED → REJECTED`
- 反证要求重大修改：`RED_TEAMED → REVISE → SCORED`
- 反证导致改选：原候选 `RED_TEAMED → REJECTED`，替代候选进入 `SELECTED`

## 4. Decision Record

| Field | Required | Description |
|---|---:|---|
| `decision_id` | 是 | 唯一标识 |
| `stage` | 是 | 市场、评分、推荐、反证、选型、范围 |
| `question` | 是 | 要解决的具体决策 |
| `decision` | 是 | 已选择结论 |
| `evidence_refs` | 是 | 岗位、能力信号、候选或实验引用 |
| `rationale` | 是 | 证据如何支持结论 |
| `alternatives` | 是 | 被考虑的替代方案 |
| `uncertainty` | 是 | 剩余不确定性 |
| `revisit_trigger` | 是 | 什么新证据会重开决策 |
| `status` | 是 | proposed / accepted / superseded |

## 5. Project Specification

最终选定项目的权威产品规格。必须含 A～Q 全部章节、版本、选中候选、范围边界、关联决策记录以及验收状态。只有一个版本可处于 `current`。

## 6. Agent Scenario

| Field | Required | Description |
|---|---:|---|
| `scenario_id` | 是 | 唯一标识 |
| `title` | 是 | 业务可读名称 |
| `user_input` | 是 | 用户任务与上下文 |
| `agent_decision` | 是 | 需要模型判断之处 |
| `business_data` | 是 | 查询或变更的数据 |
| `tool_sequence` | 是 | 允许/期望工具与条件 |
| `retrieval_need` | 是 | none / optional / required，并给理由 |
| `approval_rule` | 是 | 无、条件审批或必审 |
| `expected_output` | 是 | 用户可验证的结果 |
| `failure_modes` | 是 | 超时、误选、重复、越权、注入、部分失败等 |
| `acceptance_oracle` | 是 | 如何判定成功、合规与安全 |

## 7. Tool Contract

工具记录包含名称、业务功能、输入/输出模式、读写属性、风险等级、自动调用策略、授权、审批、超时、重试、幂等键、错误类型、审计字段和禁止行为。写工具必须有业务系统侧校验，不能只依赖提示词。

## 8. Evaluation Case

| Field | Required | Description |
|---|---:|---|
| `case_id` | 是 | 稳定、可版本化标识 |
| `dataset_split` | 是 | dev / test；优化期间不得读取 test 答案 |
| `category` | 是 | happy path、tool、parameter、policy、unsafe、retrieval、failure injection 等 |
| `user_task` | 是 | 输入任务 |
| `initial_business_state` | 是 | 可重置的初始状态 |
| `allowed_tools` | 是 | 策略允许集合 |
| `expected_calls` | 否 | 可接受的工具/参数约束，不要求唯一轨迹时使用谓词 |
| `forbidden_actions` | 是 | 必须为零的危险行为 |
| `expected_business_state` | 是 | 任务后的状态或不变约束 |
| `expected_answer_facts` | 是 | 最终答复必须/不得包含的事实 |
| `citation_expectation` | 否 | 检索场景的证据要求 |
| `scorers` | 是 | 确定性检查优先，模型裁判需版本化并抽查 |
| `tags` | 是 | 难度、风险、能力和回归标签 |

## 9. Weekly Deliverable

包含周次、可运行增量、演示路径、验收标准、本人必须掌握内容、可由 AI 辅助内容、预算、依赖、风险、降级项和完成证据。第 2 周前必须产生纵向切片。

## 10. Evidence-backed Resume Claim

| Field | Required | Description |
|---|---:|---|
| `claim_id` | 是 | 唯一标识 |
| `text` | 是 | 简历表述 |
| `status` | 是 | target / measured / approved；只有 approved 可作成果 |
| `evaluation_run_refs` | 条件 | measured/approved 必填 |
| `dataset_version` | 条件 | 含数字时必填 |
| `metric_definition` | 条件 | 含数字时必填 |
| `limitations` | 是 | 数据规模、模型、成本和适用范围 |
| `reviewed_at` | 条件 | approved 必填 |

## Relationships

- `Job Posting Sample` 多对多支持 `Capability Signal`。
- `Capability Signal` 多对多支持 `Project Candidate` 的需求匹配评分。
- 多个 `Project Candidate` 通过 `Decision Record` 产生一个 `Project Specification`。
- `Project Specification` 包含多个 `Agent Scenario`、`Tool Contract`、`Evaluation Case` 和 `Weekly Deliverable`。
- `Evidence-backed Resume Claim` 必须引用后续实际 `Evaluation Run`；没有运行记录时只能保持 `target`。
