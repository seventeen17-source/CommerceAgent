# CommerceAgent Project Progress

> 这是项目的唯一阶段导航文件。每次开始开发先看这里，再去 `tasks.md` 找当前阶段任务。
>
> ⚠️ **你正在读 `main` 上的这一份。它只描述 `main` 自己的历史，不代表项目的当前进度。**

## main 的定位与进度判断的唯一入口（务必先读这一段）

`main` 只保留**已经合并的里程碑**，所以本文件与 `tasks.md` 在 `main` 上**天然滞后于实际开发**。这不是笔误，也不代表工作没做。

**进度判断的唯一入口**：

```text
分支：origin/dev/002-commerce-after-sales-mvp
文件：PROJECT_PROGRESS.md
```

- 讨论「项目现在做到哪」，一律以该分支（及其后续 `feat/*` checkpoint 分支）的 `PROJECT_PROGRESS.md` 为准；
- **本文件中出现的任何 T 号、勾选框与分支清单都只描述 `main` 的历史，不得用来推断当前进度**；
- 判断进度前先固定事实基准：`git fetch --all --prune`，然后写出 `git branch --show-current` 与 `git rev-parse HEAD`；比较领先/落后一律用 `origin/dev/...`，不要用可能指向历史归档线的本地同名分支；
- **不要因为本文件提到某个 T 号，就认为它是「当前活跃任务」。** 本段刻意不再记录任何「当前活跃分支 / 当前活跃任务」：上一版把 `foundation/t016-contract-hardening` 标注为「👈 当前活跃分支（领先 main 119 个提交）」、并写明「真实活跃任务是 T016」，而那块路标在 2026-09-19 之后持续过期，已导致多个 Agent 把进度误判回 T016/T017 时代。**过期路标比没有路标更有害**，因为它会被当成权威，所以这里改为只指向机制、不指向 T 号。
- `main` 的滞后是**预期行为**，不是需要「修复」的状态：按 `AGENTS.md` §6，合并到 `main` 前需要用户明确确认。

历史分支（`setup/*`、`foundation/*`、`feat/*`）按 §6 保留为可回退 checkpoint，不再逐一列在本文件里（它们会过期）。要看真实的分支与时间线，用 git：

```powershell
git fetch --all --prune
git log --all --date=short --pretty='%h %ad %d %s'
```

## 当前状态（仅描述 `main` 自身）

- **本节效力范围**：以下全部内容**只描述 `main` 上已合并的东西**。项目当前进度不在这里，见上方「进度判断的唯一入口」。
- **`main` 已并入**：Phase 0 设计冻结、Phase 1 官方脚手架（T002–T004，`098e3fc`）。
- **`main` 上不含**：T005 起的全部实现（Phase 1 收尾，以及 Phase 2 起的 Foundation / US1 / …）都在 `dev/002-commerce-after-sales-mvp` 及其 feature 分支上。
- **`main` 上已完成**：
  - T002 — Spring Initializr 生成 `commerce-backend/`（Java 21 / Spring Boot 4.1.1），`mvnw.cmd test` BUILD SUCCESS（用户本地复核）
  - T003 — `uv init` 生成 `agent-service/`、依赖已加入、`uv.lock`（58 包）；复核通过：`uv run python --version` → `Python 3.13.14`、关键导入 smoke test `imports OK`（用户本地复核）
  - T004 — Vite 生成 `web/`、`npm install` 完成、`npm run build` 成功产出 `dist/`（用户本地复核，用 `npm.cmd`，见下）
- **`main` 上的待办**：T005–T007 从未并入 `main`，但它们早已在 `dev/002-commerce-after-sales-mvp` 的历史中完成——**不要因为这里写着 T005–T007 就重做它们**。
- **下一 Gate（就 `main` 而言）**：Java / Python / Web 三个官方脚手架均可启动，基础目录与依赖符合 Plan，Git diff 干净
- **当前 Blocker**：无（JDK 21 / Docker Desktop / Maven 本地仓库 / npm 代理 7892 均已就绪）
- **环境注意**：本机 PowerShell 执行策略为默认 `Restricted`，`npm` 会命中被拦的 `npm.ps1`；**前端命令一律使用 `npm.cmd` / `npx.cmd`**。
- **未决项**：
  - T001 的目录部分（`eval/`、`knowledge/policies/`、`infra/`）按决策交由各自产出任务创建，故 T001 暂不勾选
  - `.specify/feature.json` 是 Spec Kit 的**本地活动 feature 状态**，不作为仓库 Source of Truth、也不提交；运行 Spec Kit 前应在本地确认它解析到 `specs/002-commerce-after-sales-agent`
- **明确延期**：US6 Policy/RAG、独立 Eval Dashboard、MCP、Multi-Agent、Kafka、Kubernetes、花哨 UI

## 阶段总览

> 下表的「状态」列只描述 **`main` 上已合并的内容**，不代表项目当前进度；当前进度见上方「进度判断的唯一入口」。

| Phase | 目标 | Tasks | Gate | 状态（仅 `main`） |
|---|---|---|---|---|
| 0 | 设计冻结 | — | 002 Spec / Plan / Tasks / Contracts 已对齐 | ✅ 已并入 `main` |
| 1 | 官方项目脚手架 | T001–T007 | Java / Python / Web 可启动，PostgreSQL 基础配置就绪 | 🟡 仅 T002–T004 已并入 `main`；T005–T007 从未并入 |
| 2 | Foundation | T008–T018 | AgentRun / Auth / DB boundary / Trace 基础能力可用 | ⬜ `main` 上无任何实现内容 |
| 3 | US1 MVP | T019–T035 | 物流异常 → eligibility → refund → verification 真实 E2E 跑通 | ⬜ 不代表当前进度 |
| 4 | Agent Value | T036–T048 | 同类请求可因证据走退货 / 澄清等不同路径 | ⬜ 不代表当前进度 |
| 5 | HITL | T049–T056 | 高风险动作等待权威审批并可恢复执行 | ⬜ 不代表当前进度 |
| 6 | 安全降级 | T057–T063 | 依赖失败 / 规则冲突时 Safe Stop 或转人工 | ⬜ 不代表当前进度 |
| 7 | Policy / RAG | T064–T070 | 政策证据可检索引用，但不掌握资金授权 | ⬜ 不代表当前进度 |
| 8 | Eval & Portfolio | T071–T083 | Eval、CI、Docker、README、Demo、真实指标完成 | ⬜ 不代表当前进度 |

## Phase 1 — `main` 上的执行顺序（历史记录，非当前工作）

1. ✅ 拉取最新 `main` 并确认工作区干净
2. ℹ️ `.specify/feature.json` 仅为本地 Spec Kit 状态；不提交到仓库。运行 Spec Kit 前本地确认活动 feature 为 `specs/002-commerce-after-sales-agent`
3. ✅ 创建分支：`setup/official-scaffolds`
4. 🟡 T001：仓库目录 / README / ignore 基础检查（README 已满足且未新建；6 个根目录交由各产出任务创建，故本任务暂不勾选）
5. ✅ T002：用 Spring Initializr 生成 `commerce-backend`（Java 21 / Spring Boot 4.1.1；`mvnw.cmd test` BUILD SUCCESS）
6. ✅ T003：用 `uv init` 初始化 `agent-service`（Python 3.13.14，导入 smoke 通过，`uv.lock` 58 包）
7. ✅ T004：用 Vite 生成 `web`（`npm install` 完成，`npm.cmd run build` 成功产出 `dist/`）
8. ⬜ 检查 `git status` / `git diff`
9. ✅ 对三个脚手架分别做最小 build / smoke test（Java BUILD SUCCESS / Web vite build 成功 / Python `uv sync` + 导入 smoke）
10. ⬜ 再进入 T005–T007（PostgreSQL / Docker Compose / 环境基础配置）

## Phase 1 完成标准

只有同时满足以下条件，才进入 Phase 2：

- [x] Java 工程由 Spring Initializr 官方生成
- [x] Maven Wrapper 可用
- [x] Java 版本与 Plan 一致（Java 21；Spring Boot 经决策由 3.5.x 升为 4.1.1）
- [x] Python 工程由 `uv init` 生成
- [x] Python 版本与 Plan 一致，保留 `uv.lock`
- [x] React + TypeScript 工程由 Vite 生成
- [x] 三个工程最小启动 / build 成功
- [ ] PostgreSQL / Docker Compose 基础环境可启动
- [x] 没有提前加入 US6 / MCP / Multi-Agent 等非当前依赖
- [ ] Git diff 只包含预期脚手架和基础配置
- [x] 当天 `docs/devlog/YYYY-MM-DD.md` 已记录真实进展、问题、决策和 Git 证据（2026-09-16 记 T001/T002；2026-09-17 记 T003/T004）

> 「三个工程最小启动 / build 成功」的实测依据：Java `mvnw.cmd test` BUILD SUCCESS（含 Testcontainers 起真实 PostgreSQL）；Web `npm.cmd run build` 产出 `dist/`；Python `uv run python --version` → 3.13.14 且关键库导入成功。Python 的应用入口（`app/main.py`）属 T018，本阶段不涉及。
> 「Git diff 只包含预期脚手架和基础配置」尚未勾选：三个脚手架已在 `setup/official-scaffolds` 上分逻辑提交，待确认工作区无其它改动后再勾。

## 维护规则

- 每完成一个 Gate 更新本文件；不要每天机械改百分比。
- 每次开发只关注当前 Phase，不主动扩展下一阶段。
- `tasks.md` 是详细执行清单，本文件只做导航，不复制全部 Task 内容。
- 实际代码行为与本文不一致时，以 Constitution / Spec / Plan / Tasks 为准，并及时更新本文件。
- **进度判定的唯一权威 ref 是 `origin/dev/002-commerce-after-sales-mvp`**；`main` 的 `PROJECT_PROGRESS.md` 与 `tasks.md` 只描述 `main` 自身历史。
- **在 `main` 上不要写「当前活跃分支 / 当前活跃任务」这类会过期的路标**：只写「进度去哪个分支看」这个机制。过期路标比没有路标更有害——它会被 Agent 当成权威，把进度误判回旧阶段（本文件 2026-09-19 那版就是这么把多个 Agent 引到 T016/T017 的）。
