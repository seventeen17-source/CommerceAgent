# CommerceAgent Project Progress

> 这是项目的唯一阶段导航文件。每次开始开发先看这里，再去 `tasks.md` 找当前阶段任务。

## 当前状态

- **当前 Phase**：Phase 1 — 项目脚手架
- **当前 Tasks**：T001–T007
- **已完成**：T002 — Spring Initializr 生成 `commerce-backend/`（Java 21 / Spring Boot 4.1.1），`mvnw.cmd test` BUILD SUCCESS
- **当前优先任务**：T003–T004
- **下一 Gate**：Java / Python / Web 三个官方脚手架均可启动，基础目录与依赖符合 Plan，Git diff 干净
- **当前 Blocker**：无（JDK 21 / Docker Desktop / Maven 本地仓库均已就绪）
- **未决项**：
  - T001 的目录部分（`eval/`、`knowledge/policies/`、`infra/`）按决策交由各自产出任务创建，故 T001 暂不勾选
  - `.specify/feature.json` 本地仍指向 `specs/001-agent-career-project`，按执行顺序第 2 步应指向 002
- **明确延期**：US6 Policy/RAG、独立 Eval Dashboard、MCP、Multi-Agent、Kafka、Kubernetes、花哨 UI

## 阶段总览

| Phase | 目标 | Tasks | Gate | 状态 |
|---|---|---|---|---|
| 0 | 设计冻结 | — | 002 Spec / Plan / Tasks / Contracts 已对齐 | ✅ Complete |
| 1 | 官方项目脚手架 | T001–T007 | Java / Python / Web 可启动，PostgreSQL 基础配置就绪 | 👉 Current（T002 ✅） |
| 2 | Foundation | T008–T018 | AgentRun / Auth / DB boundary / Trace 基础能力可用 | ⬜ |
| 3 | US1 MVP | T019–T035 | 物流异常 → eligibility → refund → verification 真实 E2E 跑通 | ⬜ |
| 4 | Agent Value | T036–T048 | 同类请求可因证据走退货 / 澄清等不同路径 | ⬜ |
| 5 | HITL | T049–T056 | 高风险动作等待权威审批并可恢复执行 | ⬜ |
| 6 | 安全降级 | T057–T063 | 依赖失败 / 规则冲突时 Safe Stop 或转人工 | ⬜ |
| 7 | Policy / RAG | T064–T070 | 政策证据可检索引用，但不掌握资金授权 | ⬜ Optional/P2 |
| 8 | Eval & Portfolio | T071–T083 | Eval、CI、Docker、README、Demo、真实指标完成 | ⬜ |

## Phase 1 — 当前执行顺序

1. ✅ 拉取最新 `main` 并确认工作区干净
2. ⬜ 本地 `.specify/feature.json` 指向 `specs/002-commerce-after-sales-agent`（当前仍为 001）
3. ✅ 创建分支：`setup/official-scaffolds`
4. 🟡 T001：仓库目录 / README / ignore 基础检查（README 已满足且未新建；6 个根目录交由各产出任务创建，故本任务暂不勾选）
5. ✅ T002：用 Spring Initializr 生成 `commerce-backend`（Java 21 / Spring Boot 4.1.1；`mvnw.cmd test` BUILD SUCCESS）
6. ⬜ T003：用 `uv init` 初始化 `agent-service`
7. ⬜ T004：用 Vite 初始化 `web`
8. ⬜ 检查 `git status` / `git diff`
9. 🟡 对三个脚手架分别做最小 build / smoke test（Java 已验证通过；Python / Web 待做）
10. ⬜ 再进入 T005–T007（PostgreSQL / Docker Compose / 环境基础配置）

## Phase 1 完成标准

只有同时满足以下条件，才进入 Phase 2：

- [x] Java 工程由 Spring Initializr 官方生成
- [x] Maven Wrapper 可用
- [x] Java 版本与 Plan 一致（Java 21；Spring Boot 经决策由 3.5.x 升为 4.1.1）
- [ ] Python 工程由 `uv init` 生成
- [ ] Python 版本与 Plan 一致，保留 `uv.lock`
- [ ] React + TypeScript 工程由 Vite 生成
- [ ] 三个工程最小启动 / build 成功
- [ ] PostgreSQL / Docker Compose 基础环境可启动
- [x] 没有提前加入 US6 / MCP / Multi-Agent 等非当前依赖
- [ ] Git diff 只包含预期脚手架和基础配置
- [x] 当天 `docs/devlog/YYYY-MM-DD.md` 已记录真实进展、问题、决策和 Git 证据（2026-09-16）

## 维护规则

- 每完成一个 Gate 更新本文件；不要每天机械改百分比。
- 每次开发只关注当前 Phase，不主动扩展下一阶段。
- `tasks.md` 是详细执行清单，本文件只做导航，不复制全部 Task 内容。
- 实际代码行为与本文不一致时，以 Constitution / Spec / Plan / Tasks 为准，并及时更新本文件。
