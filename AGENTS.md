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

## 2. 默认教学模式：Map-first Project Teaching Protocol

**本仓库的教学协议高于任何单独 Skill。** 任何 Agent（ChatGPT / Codex / 其他编码 Agent）进入本仓库后，只要执行开发、调试、架构、测试或教学任务，就必须先遵守 `docs/LEARNING_PROTOCOL.md`。即使当前环境没有安装 `project-coding-tutor`，也不得退化为“只完成任务、不解释项目位置”的赶工模式。

`project-coding-tutor` 仍可作为辅助 Skill 使用，但它不是本仓库教学规则的唯一载体，也不能覆盖 `docs/LEARNING_PROTOCOL.md`。

对以下任务，必须使用该仓库教学协议：

- 编写或修改实现代码；
- 调试错误；
- 设计/调整架构；
- 编写关键测试；
- 学习 Spring / Python / FastAPI / LangGraph / Agent 工程；
- 解释项目中的关键机制或准备面试。

教学协议的规范来源：`docs/LEARNING_PROTOCOL.md`。

如果 `project-coding-tutor` 已作为全局/本地 Skill 安装，可以调用它辅助执行；CommerceAgent 仓库中的自定义 Skill 源码统一维护在 `skills_` 分支。不要为了让当前工作分支可见而把 Skill 源码复制回 `main` 或功能分支。

### 每个 Txxx 开始前的强制定位卡

任何 Agent 在开始实现一个 Txxx 前，必须先用用户能理解的语言回答以下 8 项，**然后才能进入代码**：

1. **当前阶段**：现在属于 Setup / Foundation / US1 / US2 / Clarification / HITL / Failure Recovery / RAG / Eval 中哪一阶段；
2. **当前系统层**：Web / Agent API / Agent Brain / Tool / Java Business / Data / Cross-cutting Safety & Eval 中哪一层；
3. **上游是谁**：谁会调用当前组件；
4. **下游是谁**：当前组件会调用谁；
5. **输入是什么**；
6. **输出是什么**；
7. **它解决什么问题，不做会怎样**；
8. **它在最终 Agent 主链中的位置**，必须画出 3–8 行的小数据流图。

如果用户表现出“我只是在搭环境、不知道自己在干什么”的感觉，Agent 必须优先恢复这张定位图，而不是继续堆代码。

### 每个 Txxx 的固定教学顺序

默认顺序必须是：

`总体地图定位 → 本 T 的局部链路 → 1–2 个核心概念 → 预测/设计 checkpoint → 小步实现 → 可执行验证 → 失败模式复盘 → 面试压缩`

禁止顺序：

`直接改一堆文件 → 跑绿 → 告诉用户完成`

对 B-class 样板工作可以加速，但仍必须说明“它在总图哪一层、连接谁、为什么存在”。

### Visible Output（可见产出）规则

用户容易在连续的 Foundation / Runtime 工作中出现“理解了流程，但学完仍然很空”的感觉。因此，**每个 Txxx 收尾时都应尽量留下一个可运行、可观察、可讲解的小产出**，不能只留下“代码已提交 / 测试已通过”。

默认要求：

1. **能跑**：至少有一条明确命令可以启动、执行或验证；
2. **能看到结果**：优先使用小 Demo、Playground、测试页、CLI 输出、Trace、数据库状态或 API 响应；
3. **能对应本 T 的代码**：必须让用户看得出“哪几个文件/模块参与了这次流转”；
4. **能解释输入 → 处理 → 输出**：关键步骤可以被展开或复述，而不是只显示最终成功；
5. **不提前伪造后续能力**：当前 T 未实现 LangGraph / FastAPI / 写操作时，Visible Output 必须明确使用 mock / simulation，不得让展示看起来像真实链路已经完成；
6. **不污染下一阶段**：产出应尽量复用现有项目，以最小代码实现；教学 UI 属于 B-class，不应为了“好看”引入重依赖或改变核心架构；
7. **必须优先在同一个 Flow Playground 上递进叠加**：默认不是“每个 T 做一个新的孤立 Demo”，而是持续扩展现有 `web/` 测试站点（本地开发默认入口 `http://localhost:5173/`）。前一个 T 的流转保留，后一个 T 在其基础上继续增加节点、真实调用、状态、Trace 或失败恢复；
8. **新能力要叠在旧流转上**：页面应逐步从“静态 mock 教学图”成长为“真实 Agent 调试台”。除非技术上明显不适合，新的 Visible Output 应接到已有主链，而不是另起一个互不相干页面；
9. **可用于面试复述**：阶段结束时给出一句“我做出了什么”的可直接表述版本。

持续叠加路线：

```text
同一个 http://localhost:5173/

T016
用户场景
  → AuthContext
  → CommerceClient
  → Java mock
  → typed response
  → AgentState

T017 在上面的流转继续叠加
  → AgentRun
  → ToolExecution
  → checkpoint save
  → process restart / resume
  → trace persistence

T018 继续叠加
  → 页面请求真实 FastAPI
  → JWT / security
  → 创建或恢复 AgentRun
  → 后端真实返回流转数据

T019+ 继续叠加
  → 用户自然语言
  → LangGraph / Routing
  → Tool
  → CommerceClient
  → Java
  → PostgreSQL
  → AgentState / Trace / Audit

最终：
同一个页面逐步成长为 CommerceAgent Flow Playground / Debug Console
```

原则：**能在原有流转上增加，就不要另做一个割裂的新 Demo。** 只有当某个能力无法合理放入该页面时，才使用 CLI / SQL / 独立测试等辅助产出，并尽量把结果或链接回挂到 Flow Playground。

如果某个 Txxx 确实不适合做 UI，也必须至少留下一个**可执行/可观察的等价产出**（例如测试、Trace、SQL 验证、CLI demo），并解释为什么它已经足够代表本阶段能力。

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

### 面试检查点：高频重点必须主动提问

开发过程中，只要遇到**面试中高频、核心、容易被连续追问**的知识点，Agent 必须把它视为一个 interview checkpoint，而不是直接实现后略过。

执行方式：

1. 先明确告诉用户：这里出现了一个值得面试掌握的重点；
2. 在给出完整答案前，先向用户提出 1 个简短但有区分度的问题，让用户先回答、预测或做设计选择；
3. 用户回答后，再判断其理解是否准确，补充缺失点并纠正误区；
4. 解释面试官为什么常问这个点，以及通常会继续追问什么；
5. 最后把该知识点压缩成一段用户能在面试中直接讲出的回答。

优先触发范围包括但不限于：

- transaction / isolation / lock / optimistic locking；
- idempotency / retry / timeout / unknown write recovery；
- JWT / authentication / authorization / ownership；
- Spring Bean / DI / AOP / transaction boundary；
- HTTP / REST / status code / API contract；
- PostgreSQL index / constraint / transaction / role privilege；
- Docker network / port mapping / container lifecycle；
- Agent State / State Machine / checkpoint / resume；
- Tool Calling / allowlist / authority boundary；
- HITL / approval / failure recovery；
- concurrency / race condition / consistency；
- Eval / Trace / observability；
- Java 与 Python Agent 的系统边界和重要架构取舍。

不要对普通样板代码、简单语法或低价值细节频繁打断；只有当知识点具备明显面试价值，或者当前实现依赖用户真正理解该机制时，才触发该规则。

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


## 9. Java 质量门禁规则

Java 代码的任务验收必须以完整质量门禁为准，而不是“代码写完”或“测试通过”即完成。

固定规则：

1. 新增或修改 Java 文件时，提交前必须按仓库 Spotless / Palantir Java Format 约定整理；不要把格式修复长期留给用户本地。
2. `mvnw.cmd verify` 是 Java 任务的最终验收命令；只有看到 **BUILD SUCCESS** 才能把对应 Txxx 标记为完成。
3. 单元/集成测试全部通过但 Spotless 或 SpotBugs 失败时，任务仍然是“待验收”，不得提前勾选。
4. SpotBugs 告警必须先判断是否代表真实设计问题：
   - 如果是领域对象可变引用泄漏、序列化问题、并发/资源问题等真实缺陷，应优先修设计；
   - 如果是框架约定导致的可证明误报（例如 Spring singleton 构造器注入被 `EI_EXPOSE_REP2` 误判），允许做**最窄范围**的 exclude/suppression，并在代码或配置中写清理由；
   - 禁止为了过门禁全局关闭整个 SpotBugs bug pattern。
5. 不允许通过修改 `verify` 生命周期让 Spotless/SpotBugs 自动忽略失败；`verify` 保持“检查而不偷偷修源代码”的验收语义。
6. 用户本地是最终构建事实来源；远端提交成功不等于本地验收成功。

本规则适用于后续所有 Java Txxx 任务，无需用户重复提醒。
