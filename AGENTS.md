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

### 持续验证页规则

`web/` 中用于本地流转验证的页面是从 T016 开始持续升级的 **CommerceAgent Flow Playground**，不是当前任务的临时快照，也不是每个任务重新开一张页面。

- T016 的调用链、故障注入按钮和步骤解释是稳定基线；后续任务在**同一个 Flow Playground** 中增加测试按钮、状态查看器或真实数据能力；
- 页面布局职责固定为三区：上方“故障注入”增加场景按钮；左侧“调用链”按真实执行顺序追加新的主链步骤/接口；右侧 `STEP DETAIL` 同时展示当前步骤的输入、处理、输出、真实请求控件与原始响应。不得在调用链下方按 Txxx 另开验证区块；
- 左侧调用链只记录会进入端到端主流程、且值得逐步观察的节点。辅助查询、纯调试端点或同一步内部 HTTP 调用放在对应步骤的右侧详情中，不要求每个接口都机械新增一步；
- 内部允许按任务拆分 React 组件，但视觉与操作上必须保持一条连续的调试链路，不得按 Txxx 纵向堆成互不关联的独立页面；
- 默认只追加或扩展当前任务自己的控制能力，不得整体替换 `App.tsx`，也不得删除、改写先前任务的验证能力；
- 确需重构宿主结构时，必须先证明既有区块仍可访问、既有流转仍可执行，并在 devlog 记录迁移理由与验证证据；
- 真实产品 UI 仍按对应业务任务实现；Playground 不冒充最终产品，但会从教学模拟器逐步长成 Agent 调试器与 Demo Console。

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

**长期规则：一个功能 = 一个独立 feature 分支。禁止把后续功能继续从前一个 feature 分支上“套娃”创建。**

实现阶段使用一条集成开发线 `dev/002-commerce-after-sales-mvp`：

```text
main                         ← 稳定 Gate
└─ dev/002-commerce-after-sales-mvp
   ├─ feat/<feature-a>
   ├─ feat/<feature-b>
   └─ feat/<feature-c>
```

每个功能的标准流程：

1. 从**最新 dev 集成线**创建一个见名知意的 `feat/... `分支；
2. 只在该 feature 分支完成这个功能、测试和文档；
3. 验收通过后，保留该 feature 分支作为可回退 checkpoint；
4. 把已验收功能合入/快进到 `dev/002-commerce-after-sales-mvp`；
5. 下一个功能必须重新从更新后的 dev 创建新 feature 分支，**不得从上一个 feature 分支继续派生**；
6. 只有达到明确阶段 Gate，并且用户明确确认后，才把 dev 合入 `main`。

这样“依赖前一个功能”通过 dev 集成线解决，而不是通过 feature→feature 的父子嵌套解决。

要求：

- 分支名表达**功能/能力**，例如 `feat/us1-logistics-http-api`，不要仅用模糊编号；
- 每个 feature 分支是一个独立 checkpoint；历史已存在的 T019–T024 分支继续保留，不删除、不重写；
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
