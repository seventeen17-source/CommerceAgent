# CommerceAgent — Persistent Agent Instructions

本文件是 CommerceAgent 仓库的长期协作入口。进入本仓库进行开发、调试、架构修改或测试时，先读取本文件，再读取当前阶段对应的权威文档。

## 1. 权威文档顺序

按以下顺序理解项目，冲突时前者优先：

1. `.specify/memory/constitution.md` — 最高工程约束
2. `specs/002-commerce-after-sales-agent/spec.md` — 当前产品/业务规格
3. `specs/002-commerce-after-sales-agent/plan.md` — 当前技术与架构计划
4. `specs/002-commerce-after-sales-agent/tasks.md` — 实施任务清单
5. `specs/002-commerce-after-sales-agent/contracts/` — API / Tool / Error 契约
6. `PROJECT_PROGRESS.md` — 当前实施阶段与下一 Gate
7. `docs/devlog/` — 每次实际开发后的学习与决策记录

`specs/001-agent-career-project/` 已完成，只作为招聘研究、选题和历史决策证据，不作为当前实现的直接规格。

## 2. 默认教学模式：project-coding-tutor

对以下任务，必须优先使用 `project-coding-tutor` 的教学方式：

- 编写或修改实现代码；
- 调试错误；
- 设计/调整架构；
- 编写关键测试；
- 学习 Spring / Python / FastAPI / LangGraph / Agent 工程；
- 解释项目中的关键机制或准备面试。

Skill 的规范来源：`seventeen17-source/project-coding-tutor`。

如果该 Skill 已作为全局/本地 Skill 安装，则直接调用它。CommerceAgent 仓库中的自定义 Skill 源码统一维护在 `skills_` 分支；不要为了让当前工作分支可见而把 `project-coding-tutor` 复制回 `main` 或功能分支。

### Skill 分支规则

- `main` / 功能分支允许保留 **Spec Kit 初始化自动生成的 `.agents/skills/speckit-*` 项目工具**；它们属于当前仓库的 Spec Kit 工作流资产。
- `project-coding-tutor` 等**自定义 Skill**统一放在 `skills_` 分支，或安装为本地/全局 Skill；不得因为合并其他阶段分支而顺带带回 `main`。
- 如果 `AGENTS.md` 声明需要某个自定义 Skill，但当前环境不可发现，应先解决安装/发现问题，而不是复制 Skill 源码污染业务分支。

默认使用 **Level 2 — Pair**。

教学要求：

- 默认使用中文解释，代码、类名、字段、API、命令和错误信息保持原始技术语言；
- 每一步最多引入 1–2 个新的核心概念；
- 优先把 Python / FastAPI / LangGraph 概念与用户熟悉的 Java / Spring 做准确类比，同时说明类比失效的位置；
- 不要求用户手写无教学价值的样板代码；
- 不允许把关键机制静默交给 AI 实现后就视为“已学会”。

### A-class：必须真正掌握

以下内容默认属于 A-class：

- Agent State / State Machine；
- Tool Calling 与 allowlist；
- Java 与 Agent 的权威边界；
- JWT / ownership / authorization；
- transaction / idempotency；
- timeout / retry / unknown write recovery；
- checkpoint / resume；
- HITL；
- failure recovery；
- Eval / Trace；
- 重要架构取舍。

对 A-class 内容，至少完成：

1. 先解释“没有它会出什么问题”；
2. 解释最小机制与数据流；
3. 让用户完成一次预测、小修改或设计选择；
4. 至少考虑一个真实失败模式；
5. 用测试、Trace、日志、DB 状态或 API 结果验证；
6. 阶段结束时做简短掌握检查和面试压缩。

### B-class：允许 AI 加速

DTO、普通 CRUD wiring、fixture、样板配置、机械映射、样式性 UI 等可以由 AI 更直接完成，但仍需简要说明它在系统中的位置。

## 3. 每次开发先看“现在该干嘛”

开始一次开发会话前：

1. 读取 `PROJECT_PROGRESS.md`；
2. 找到当前 Phase；
3. 只读取该 Phase 对应的 `tasks.md` 任务；
4. 明确本次会话的一个小目标；
5. 未完成当前 Gate 前，不主动扩展到后续阶段或 Nice-to-have。

不要一次把 83 个 Task 全部当作当前工作。

## 4. 进度维护规则

`PROJECT_PROGRESS.md` 是唯一的阶段导航文件。

每完成一个有意义的阶段或 Gate 后更新：

- 当前 Phase；
- 已完成任务；
- 当前任务；
- 下一 Gate；
- Blocker；
- 明确延期/不做的范围。

不要维护额外的重复甘特图、复杂 Excel 日报或人为“完成百分比”。

## 5. Devlog 规则

每次实际开发会话结束后，在 `docs/devlog/YYYY-MM-DD.md` 创建或更新当天记录。保持 3–5 分钟可完成，至少包含：

- 今日目标；
- 今日完成；
- 遇到的问题；
- 关键决策；
- 今天学到；
- 下一步；
- Git 证据（branch / commit / task IDs）。

重点记录“为什么这样设计”和“踩了什么坑”，使其以后能直接用于 README、简历和面试复盘。

## 6. Git 与回退规则

实现阶段默认从最新 `main` 创建见名知意的分支。每个阶段/可独立回退的逻辑部分应形成独立分支或清晰的逻辑提交，使回退不会影响无关后续工作。

要求：

- 分支名表达阶段或能力，例如 `setup/official-scaffolds`、`feat/us1-logistics-refund`；
- commit 信息表达一个逻辑变化；
- 不修改无关文件；
- 合并到 `main` 前需要用户明确确认；
- 不为了“看起来整洁”重写已经有价值的历史。

## 7. 脚手架规则

项目初始化必须优先使用官方生成器，不得手写伪造官方脚手架：

- Java：Spring Initializr；
- Python：`uv init`；
- Frontend：Vite；
- 基础设施：按 `plan.md` / `tasks.md` 最小化配置。

涉及当前版本、CLI 参数或框架 API 时，优先查最新官方资料；Context7 可用时可用于获取当前文档和代码示例。

脚手架生成后必须检查：

- wrapper / lockfile 是否存在；
- Java / Python / Node 版本是否符合 Plan；
- 依赖是否最小且符合任务；
- 是否出现无关目录或多余模板；
- `git status` / `git diff` 是否只包含预期改动；
- 最小 build / smoke test 是否通过。

## 8. 当前范围纪律

当前最重要顺序：

`Agent Value → safe write → idempotency → HITL → Eval → Trace → Policy/RAG`

在 US1 真实端到端闭环跑通前，不优先投入：

- Multi-Agent；
- Kafka；
- Kubernetes；
- MCP；
- 独立向量数据库；
- 花哨 UI；
- Eval Dashboard；
- 非必要微服务拆分。

所有量化成功率、性能、安全、成本结论都必须来自真实可复现 Eval，不得把目标值写成已达成结果。
