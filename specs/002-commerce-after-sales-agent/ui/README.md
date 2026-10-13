# UI-1.0 产品设计交接入口

2026-10-13。本文定义目标规格，不证明实现完成；进度只见根 PROJECT_PROGRESS.md，任务与验收只见 tasks.md。

阅读顺序：AGENTS / constitution / LEARNING_PROTOCOL / spec / plan → 本文 → [视觉系统](design-system.md) → [七页UX](pages.md) → [数据和权限](data-contract.md) → [验收](acceptance.md)。

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
