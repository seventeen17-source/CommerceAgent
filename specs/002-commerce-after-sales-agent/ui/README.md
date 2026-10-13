# UI-1.0 产品设计交接入口

2026-10-13。本文定义目标规格，不证明实现完成；进度只见根 PROJECT_PROGRESS.md，任务与验收只见 tasks.md。

阅读顺序：AGENTS / constitution / LEARNING_PROTOCOL / spec / plan → 本文 → [Console IA](console-ia.md)（导航 / 路由 / 命名 / API 映射）→ [视觉系统](design-system.md) → [七页UX](pages.md) → [数据和权限](data-contract.md) → [验收](acceptance.md)。

## 冻结范围

- [Workspace](references/workspace.png)：用户明确确定。任务队列 / Runtime Trace / Decision Context 三栏、底部 Verification、顶部 Run 信息固定，不允许重新设计。
- [Dashboard](references/dashboard.png)、[Customer](references/customer.png)：配套视觉依据。按 design-system 的语义修订落地。
- Case / Approval / Recovery / Analytics：pages.md 是尺寸及行为规格，不能声称用户已认可尚未生成的页面图片。首个实现截图建立基准，逐页评审，不能一次实现四页后才看效果。
- 旧 ui-productization 的聊天布局、三入口分段导航、仅客户端演示方案由本包取代；旧源码证据是历史定位，不是当前能力证明。
- 宪法、安全契约优先；视觉外观不得扩大权限或虚构业务事实。字段暂缺保留区域和明确文案，登记对应任务，不自行删模块或退回原始JSON。

## 页面关系

同一Web，多角色视角。Customer入口：发起售后→本人任务→案件详情。企业入口：Dashboard→Workspace→Case/Approval/Recovery；Analytics明细钻取回Workspace。原Flow Playground保留独立开发入口与既有控制，不成为产品默认页。

Operator/Admin是产品视角名称，不是浏览器可授予的权限；当前APPROVER的审批权限不自动获得客户Run、订单或物流读取权。新增运营读取必须先交付T097/T098。

## 接手规则

所有实现同时满足页面规格、数据映射、交互状态、固定场景截图与真实链路验收；build成功不等于UI完成。先冻结一页样式和组件，再扩展同一组件系统。不可擅自换配色/布局/组件库或创建第二套状态文案。

Demo适配器与Live适配器隔离；Demo标识常驻、不得触发生产写入。Live缺数据用未知/未获取/不可访问，不自动回填示例。三张PNG应随文档一并交接，不能只传任务清单。

## 已弃用与归档（2026-10-13 冻结）

下一位 Agent 先读这一节，避免重复劳动。**遇到 UX 编号（UX001–UX052）不要开工**——那条线已归档，不作路线图。**本包（`ui/` 四份文档 + `console-ia.md`）是唯一权威**；任何旧文档与本包冲突时以本包为准。

| 对象 | 位置 | 状态 | 处置 |
|---|---|---|---|
| **UX 线（方案2）** | 分支 `feat/ui-experience-layer`（10 提交，tip `f0ac3f2`）+ `specs/003-product-experience-layer/`（UX001–UX052）+ `.specify/templates/ui/DESIGN.md` + `docs/ui/ui.md` + `docs/product/commerceagent-ui-architecture.md` + `docs/api/frontend-contract.md` | 2026-10-12，**未合入 dev / main** | **归档**：只作视觉方向参考（Linear / Vercel / Agent observability 风格；Sidebar + Header + Workspace 布局）。不作路线图、不作验收依据、不复制进当前分支；需要参考时用 `git show origin/feat/ui-experience-layer:<path>`。 |
| **三库建议** | 上述 `DESIGN.md` 中的 Ant Design / React Flow / ECharts | — | **不采用**：会形成第二套视觉真相；P07 的 metrics 接口未实现；React Flow 的自由连线与“未发生不标完成”的验收冲突。 |
| **旧 T084 文档正文** | `ui-productization.md` 的 2026-10-12 版（数据来源矩阵 + 线框，252 行，提交 `b6c1639`） | 已被本包取代 | 内容搬入 `ui/` 四份文档 + `console-ia.md`；该文件现为 16 行入口壳。历史正文可查 `git show b6c1639:specs/002-commerce-after-sales-agent/ui-productization.md`。 |
| **第一次 UI 实现尝试** | 分支 `feat/frontend-product-ui`（`348dd0c`、`f59ea0f`）+ 工作树 `.worktrees/frontend-product-ui` | 2026-10-10/11，ahead 3 / behind 108 | **废弃**，仅保留为历史 checkpoint；不得在此分支或该工作树上继续开发。 |
| **并行在途外壳（未提交）** | `web/src/features/workspace/*`（WorkspaceShell、Mission Center / Run Replay / Safety Center 三屏）、`web/src/features/auth/*`、`AuthController`、`V009__user_credentials.sql`、`DemoCredentialSeeder`、`AuthLoginIntegrationTest`；被修改的 `SecurityConfig.java`、`User.java`、`commerce-api.openapi.yaml`、`web/src/App.tsx`、`CustomerConsole.tsx` | 未提交、未验收（文件时间 2026-10-12 20:09–23:22，测试 2026-10-13 20:23） | **不被本包继承**：它照 UX 线 `DESIGN.md` 写成，导航与命名与本包冲突。**删除或保留由用户决定**；任何 Agent 不得擅自删除他人未提交改动。 |
| **分支名 `feat/customer-workspace-shell`** | 本地（当前 checkout） | 名称对应方案1「传统角色售后工作台」外壳 | **暂停使用 / 待重命名**：新工作从 `feat/console-ia-freeze` 继续，后续按 `tasks.md` 的 T105–T109 分支命名。 |

判定依据（可复现）：`git ls-remote origin` 无 `specs/003` 合并记录；`git ls-tree dev/002-commerce-after-sales-mvp -- specs/003-product-experience-layer` 与 `git ls-tree main -- specs/003-product-experience-layer` 均为空。
