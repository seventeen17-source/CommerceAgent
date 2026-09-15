# Implementation Plan: 求职导向的 Agent 项目决策与设计

**Branch**: `001-agent-career-project`（逻辑 feature 标识；当前目录不是 Git 工作树） | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-agent-career-project/spec.md`

**Note**: This template is filled in by the `$speckit-plan` command; its definition describes the execution workflow.

## Summary

本计划交付一套“证据采集—能力归纳—候选评分—三角色反证—最终规格—实施路线”的文档化决策流程。第一阶段建立至少 30 条去重岗位样本和能力地图；第二阶段用固定权重、评分锚点、致命门槛和敏感性分析比较 4～6 个项目；只有推荐通过反证后，才生成 A～Q 项目规格和 6～8 周路线。当前计划不实现 Agent 应用，也不预选编程语言、框架或基础设施。

## Technical Context

**Language/Version**: N/A；本 feature 的交付物是中文研究与设计文档，后续项目的开发语言将在完成市场分析和选题后单独决策。

**Primary Dependencies**: 可追溯的公开招聘来源、网页检索能力、Markdown 文档和统一的证据记录契约；不依赖某个 Agent 框架。

**Storage**: 本 feature 使用版本化文档与结构化表格记录岗位、评分、决策和来源；最终项目的数据存储尚不在本阶段决定。

**Testing**: 来源抽查、去重检查、评分重算、阶段门检查、规格覆盖检查、交叉引用检查和独立评审。

**Target Platform**: 可在常见桌面环境和代码托管平台阅读、复核的文档包。

**Project Type**: 研究、产品决策与实施规划文档；不是可部署应用。

**Performance Goals**: 30 条以上去重岗位样本；4～6 个候选；A～Q 覆盖率 100%；8 周内每周有可运行交付；所有结论可在 15 分钟内定位到支持证据。

**Constraints**: 2026-09-15 起可访问的公开信息；目标以中国大陆 2027 校招/实习为主；单人每周约 15～25 小时；不得虚构招聘趋势、企业集成或项目指标；不得提前锁定技术栈。

**Scale/Scope**: 一次岗位市场快照、一份能力地图、4～6 个候选、一个经反证的最终项目规格、50～100 条评估样本设计和一份 6～8 周路线。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目宪章仍为占位模板，未提供可执行的治理条款。为避免无约束推进，本 feature 采用规格与用户输入中已明确的替代门槛：

- **Evidence Gate — PASS**: 外部事实必须有来源、访问日期和证据等级；推断与事实分离。
- **Sequence Gate — PASS**: 不在招聘分析和候选反证前选择项目或技术栈。
- **Agent Value Gate — PASS**: 候选必须包含真实任务执行与业务系统连接，纯聊天和简单 PDF 问答不合格。
- **Feasibility Gate — PASS**: 核心范围须由单人在 6～8 周完成，第 2 周前形成纵向切片。
- **Reliability Gate — PASS**: 最终项目必须覆盖工具安全、异常恢复、人工审批、评估和可观测性。
- **Ownership Gate — PASS**: 核心 Agent 机制必须由用户理解并能简化复现；AI 辅助不能替代设计责任。
- **Honesty Gate — PASS**: 未实测指标只能写为目标或占位符，不能作为简历成果。

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-career-project/
├── plan.md              # This file ($speckit-plan command output)
├── research.md          # Phase 0 output ($speckit-plan command)
├── data-model.md        # Phase 1 output ($speckit-plan command)
├── quickstart.md        # Phase 1 output ($speckit-plan command)
├── contracts/
│   └── artifact-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output ($speckit-tasks command - NOT created by $speckit-plan)
```

### Source Code (repository root)

```text
N/A — 当前 feature 只生成研究与规划文档。最终 Agent 项目的源代码结构必须等选题和技术论证完成后，在其独立计划中定义。
```

**Structure Decision**: 所有当前产物集中在 `specs/001-agent-career-project/`，使招聘证据、评分规则、决策记录和验收方式可版本化审查，同时避免为空项目预造代码目录。

## Phase 0 — Research Decisions

1. 建立来源层级、样本纳入/排除和去重规则，防止转载 JD 与高级岗位污染结论。
2. 为技能频次建立“硬性要求 / 加分项 / 职责语境 / 证据强度”的编码方式。
3. 为六维评分建立 1、3、5、7、9 分锚点，并设置致命门槛与敏感性分析。
4. 定义面试官、招聘经理、开发者三角色反证表，要求每项反对意见产生处置结果。
5. 明确 6～8 周范围预算、纵向切片门、评估诚信和简历证据规则。

详细决策记录在 [research.md](./research.md)。

## Phase 1 — Design & Contracts

1. 使用 [data-model.md](./data-model.md) 统一岗位样本、能力信号、候选、决策、场景、工具、评估和简历主张的数据语义。
2. 使用 [artifact-contracts.md](./contracts/artifact-contracts.md) 约束各阶段输入、输出、必填字段和退出门槛。
3. 使用 [quickstart.md](./quickstart.md) 复核从原始岗位证据到最终规格的端到端流程。

## Post-Design Constitution Check

- **Evidence Gate — PASS**: 数据模型和契约要求来源、访问日期、去重键与证据等级。
- **Sequence Gate — PASS**: 阶段契约禁止在前三阶段完成前冻结最终项目或技术栈。
- **Agent Value Gate — PASS**: 候选契约包含业务动作、工具、数据和“为何不能用确定性程序替代”。
- **Feasibility Gate — PASS**: 候选与周计划均包含范围预算、纵向切片和降级策略。
- **Reliability Gate — PASS**: 场景、工具与评估实体显式覆盖失败、安全和人工审批。
- **Ownership Gate — PASS**: 周交付与面试映射要求标注本人复现责任。
- **Honesty Gate — PASS**: 简历主张必须关联实际评估运行，否则状态只能是目标或占位符。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

无需要豁免的门槛违规。
