# Artifact Contracts

这些契约规定每一阶段何时可以退出，防止在证据不足时提前选项目、定技术栈或编写实现。

## Contract 1 — Job Market Evidence Pack

**Inputs**: 2026 年公开招聘页面、用户目标岗位与排除条件。

**Required outputs**:

- 至少 30 条去重后的核心岗位样本。
- 校招、实习和初级岗位占核心样本不少于 60%。
- 每条样本符合 `Job Posting Sample` 数据模型。
- 一份纳入、排除、去重和来源等级说明。
- 一份按岗位族和公司类型分层的能力地图。

**Exit gate**:

- 所有核心结论有可访问来源或被标注为推断。
- 高级岗位、转载和纯算法岗位未污染目标样本统计。
- 随机抽查 20% 样本时，标题、层级、职责和能力编码可复核。

## Contract 2 — Candidate Portfolio

**Inputs**: 通过 Contract 1 的能力地图、用户背景和 6～8 周约束。

**Required outputs**:

- 4～6 个业务方向不同的项目候选。
- 每个候选有业务系统、Agent 必要性、真实动作、评估方式和纵向切片。
- 六维评分和逐项理由：需求 25%、技术深度 20%、面试内容 20%、可完成性 15%、基础匹配 10%、差异化 10%。

**Scoring anchors**:

| Score | Meaning |
|---:|---|
| 1 | 与目标几乎无关或无法交付 |
| 3 | 价值有限，需重大假设或范围重构 |
| 5 | 可行但普通，证据和面试信号中等 |
| 7 | 明显匹配且可在约束内形成可信闭环 |
| 9 | 多类证据强支持、可完成、可评估且有突出面试内容 |
| 10 | 仅用于近乎无明显短板的例外方案，必须有强证据 |

**Fatal gates**: 任一项为“否”则不得直接成为首选。

1. 两周内能形成真实纵向切片。
2. 核心价值不依赖无法获得的私有数据或付费系统。
3. 存在至少一个 Agent 真正需要判断并调用工具的任务。
4. 能构造可判定的离线评估集。
5. 8 周内能同时覆盖可靠性、安全和可观测性，而非只完成 Happy Path。
6. 面试官可在 60 秒内理解业务价值。

**Exit gate**: 总分可重算；致命门槛全部通过；对单项分数上下浮动 1 分的敏感性分析不会被隐瞒。

每个分数还必须记录证据等级与可辩护区间。如果第一、第二名中心分差小于 0.5，或加权区间明显重叠，必须先执行一个 4～8 小时的限时验证，再决定是否能给出确定首选。

## Contract 3 — Recommendation and Red Team

**Inputs**: 通过 Contract 2 的候选集合。

**Required outputs**:

- 第一推荐、公司/岗位映射、MVP、最大风险和改选触发条件。
- 面试官视角：是否像真实工程、是否可追问、是否只是包装。
- 招聘经理视角：是否对应团队痛点、是否表明能尽快上手。
- 开发者视角：数据、集成、调试、成本和 8 周范围是否可信。
- 每条挑战的处置：接受风险、增加验证、降级、删除或改选。

**Exit gate**: 没有未处置的致命风险；推荐与评分、证据和用户基础一致；允许结论为“改选”。

## Contract 4 — Final Project Specification

**Inputs**: 通过 Contract 3 的选中候选与决策记录。

**Required outputs**: A～Q 完整项目规格、5～10 个 Agent 场景、工具风险表、技术决策表、50～100 条评估样本设计、架构与安全边界。

**Technology decision record**:

| Field | Required question |
|---|---|
| Enterprise value | 真实企业为何需要它？ |
| Project necessity | 不使用会缺失什么可验证能力？ |
| Learning ROI | 两个月内为何值得用户学习？ |
| Complexity cost | 增加多少新概念、运维与失败模式？ |
| Priority | Must / Should / Nice / Reject |
| Revisit trigger | 什么证据会改变决定？ |

**Exit gate**: A～Q 100% 覆盖；所有 Must 均通过三问；无为展示而存在的服务、数据库、Agent 或框架。

## Contract 5 — Implementation and Interview Plan

**Inputs**: 通过 Contract 4 的项目规格。

**Required outputs**:

- 6～8 个按周的可运行增量，第 2 周前完成纵向切片。
- 每周的验收、学习目标、风险、预算和削减项。
- Must 模块对应的面试问题与本人复现任务。
- 简历、README、Demo 模板；未测指标保持占位状态。

**Exit gate**: 每周均可独立演示；延期时有明确删除顺序；所有数字化简历主张都要求实际评估引用。

## Stage Ordering

```text
Market Evidence
  -> Capability Map
  -> Candidate Portfolio
  -> Recommendation
  -> Three-role Red Team
  -> Final Project Specification
  -> 6–8 Week Implementation & Interview Plan
```

禁止跨越阶段门。候选讨论可以在证据包完成前形成草案，但不得评分或宣称首选；技术可以作为备选研究对象，但不得在最终项目通过反证前冻结。
