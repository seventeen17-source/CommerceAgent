# Quickstart: 验证研究—选题—规划闭环

本指南验证 `001-agent-career-project` 的研究与选题产物是否完整；它不会启动 Agent 应用或安装任何技术栈。

## Prerequisites

- 已阅读 [spec.md](./spec.md)。
- 已阅读 [research.md](./research.md) 中的决策与替代方案。
- 使用 [data-model.md](./data-model.md) 和 [artifact-contracts.md](./contracts/artifact-contracts.md) 作为统一口径。

## Scenario 1 — 验证必需文件与阶段产物

在仓库根目录运行：

```powershell
Get-ChildItem specs/001-agent-career-project
Get-ChildItem specs/001-agent-career-project/artifacts
```

**Expected**：存在 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`quickstart.md`、`tasks.md`、`contracts/`、`checklists/` 与阶段产物目录。

> `.specify/feature.json` 不作为仓库必需文件。活动 feature 应由本地 Spec Kit/worktree/branch 状态解析，不应为了远程仓库校验人为提交一个易漂移的 pointer 文件。

## Scenario 2 — 验证规格没有遗留占位符

```powershell
rg -n '\[NEEDS CLARIFICATION|\[FEATURE|\[DATE\]|\$ARGUMENTS' specs/001-agent-career-project
```

**Expected**：规格与计划正文不应残留未解决占位符；质量清单中对这些字符串的规则说明可以忽略。

## Scenario 3 — 验证阶段门

抽查 [artifact-contracts.md](./contracts/artifact-contracts.md)：

1. 没有 30 条合格岗位样本时，候选不能最终评分。
2. 没有完成 Fatal Gate 时，不能产生第一推荐。
3. 没有完成三角色 Red Team 时，不能冻结最终项目规格。
4. 没有实际 Eval Run 时，简历数字只能是 target/placeholder。

**Expected**：四条都有明确输入、输出与退出门槛。

## Scenario 4 — 重算候选评分

```text
weighted_total =
  demand_match * 0.25
  + agent_depth * 0.20
  + interview_value * 0.20
  + eight_week_feasibility * 0.15
  + background_fit * 0.10
  + differentiation * 0.10
```

**Expected**：分数范围为 1.0～10.0；原始六项分数、理由和总分均可见；Fatal Gate 失败覆盖总分排名。

## Scenario 5 — 验证 Red Team 真的改变决策

从面试官、招聘经理、开发者视角各取一条最严重 challenge，检查是否关联至少一种处理：

- 删除/降级功能；
- 新增最小验证；
- 接受并记录剩余风险；
- 触发候选改选。

**Expected**：不存在“只有批评、没有处置”的致命问题。

## Scenario 6 — 验证两个月可完成性

检查最终项目计划：

- 第 1～2 周包含 User → Agent → Tool → Business System → Result。
- 每周有可运行增量与验收标准。
- Must / Should / Optional / Reject 边界清楚。
- 延期时先删非核心 UI、额外集成和高级基础设施。
- Eval、安全、Tool Reliability、Observability 不全部堆到最后一周。

## Scenario 7 — 验证简历诚信

随机抽取包含百分比、时延、成本、成功率或样本量的简历表述。

**Expected**：每项要么明确为 target，要么引用实际 Eval Run、Dataset Version 与 Metric Definition；不存在无法追溯的“提升 X%”。

## 当前阶段结论

`001-agent-career-project` 已完成它的主要职责：回答“为什么最终选择 CommerceAgent”。

真正项目实现应在独立 feature：`002-commerce-after-sales-agent` 中进行。
