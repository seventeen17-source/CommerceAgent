# Quickstart: 验证研究—选题—规划闭环

本指南验证规划产物是否足以支持下一阶段任务生成；它不会启动 Agent 应用或安装任何技术栈。

## Prerequisites

- 已阅读 [spec.md](./spec.md)。
- 已阅读 [research.md](./research.md) 中的决策与替代方案。
- 使用 [data-model.md](./data-model.md) 和 [artifact-contracts.md](./contracts/artifact-contracts.md) 作为统一口径。

## Scenario 1 — 验证活动 feature 与必需文件

在仓库根目录运行：

```powershell
Get-Content -Raw .specify/feature.json
Get-ChildItem specs/001-agent-career-project
```

**Expected**: `feature_directory` 指向 `specs/001-agent-career-project`，并存在 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`quickstart.md`、`contracts/` 和 `checklists/`。

## Scenario 2 — 验证规格没有遗留占位符

```powershell
rg -n '\[NEEDS CLARIFICATION|\[FEATURE|\[DATE\]|\$ARGUMENTS' specs/001-agent-career-project
```

**Expected**: 不应在规格或计划正文中找到未解决占位符；质量清单中对该字符串的规则说明可以忽略。

## Scenario 3 — 验证阶段门

手工抽查 [artifact-contracts.md](./contracts/artifact-contracts.md)：

1. 在没有 30 条合格岗位样本时，候选不能被最终评分。
2. 在没有完成候选致命门槛时，不能产生第一推荐。
3. 在没有完成三角色反证时，不能冻结技术栈或生成最终 A～Q 规格。
4. 在没有实际评估运行时，简历数字只能是目标或占位符。

**Expected**: 四条均能对应到明确输入、输出和退出门槛。

## Scenario 4 — 重算候选评分

对任一候选使用以下公式：

```text
weighted_total =
  demand_match * 0.25
  + agent_depth * 0.20
  + interview_value * 0.20
  + eight_week_feasibility * 0.15
  + background_fit * 0.10
  + differentiation * 0.10
```

**Expected**: 分数范围为 1.0～10.0；原始六项分数、理由和总分都可见；任何致命门槛失败会覆盖总分排名。

## Scenario 5 — 验证反证真的改变决策

从面试官、招聘经理和开发者视角各取一条最严重挑战，检查其是否关联以下至少一种结果：

- 删除或降级一个功能；
- 新增一个最小验证；
- 接受并记录剩余风险；
- 触发候选改选。

**Expected**: 不存在只有批评、没有处置的致命问题。

## Scenario 6 — 验证两个月可完成性

检查最终周计划：

- 第 1～2 周包含 User → Agent → Tool → Business System → Result。
- 每周有可运行演示和验收标准。
- Must、Should、Nice 和 Reject 明确。
- 延期时先删除非核心界面、额外集成与高级基础设施。
- 评估、安全、工具可靠性和可观测性没有被全部推到最后一周。

**Expected**: 所有条件通过；否则计划不能进入实现任务生成。

## Scenario 7 — 验证简历诚信

随机抽取所有包含百分比、时延、成本、成功率或样本量的简历表述。

**Expected**: 每项要么标注为待测目标，要么引用实际评估运行、数据集版本和指标定义；不存在无法追溯的“提升 X%”。

## Ready for Next Phase

当以上场景全部通过时，可以运行 `$speckit-tasks`，生成执行招聘调研、候选评估、反证和最终项目规格的任务清单。此时仍不应生成最终 Agent 应用的编码任务；应用实现任务应在最终项目规格通过后另建 feature。

