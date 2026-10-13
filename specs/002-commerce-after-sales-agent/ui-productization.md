# US7 CommerceAgent 产品化设计入口

UI-1.0（2026-10-13）权威设计包：[ui/README.md](ui/README.md)。**已弃用与归档的分支/文档清单**（含 UX 线、旧正文、第一次实现尝试、未提交的并行外壳）见该文件「已弃用与归档」一节。

- [统一视觉系统与交互](ui/design-system.md)
- [七页页面UX、组件与状态](ui/pages.md)
- [数据来源、权限与增量](ui/data-contract.md)
- [截图、Live Gate与Agent交接](ui/acceptance.md)

本文替代旧版聊天主界面、三入口分段导航。Agent Workspace保持已确定结构；客户采用售后申请+处理状态。同一Web包括Dashboard、Customer Portal、Agent Workspace、Case Detail、Approval Center、Recovery Center、Analytics。原Flow Playground独立保留。

设计不记录进度。阶段见[PROJECT_PROGRESS.md](../../PROJECT_PROGRESS.md)，任务见[tasks.md](tasks.md)。旧来源矩阵是历史快照，可从Git历史查阅，不作为当前接口断言；新映射按ui/data-contract.md复核。

图片中的数字、状态和按钮是示例，落地须遵守design-system.md语义修订。缺失运营权限不能前端绕过；目标只读增量由T097/T098承担。本轮不修改已发布API。

US6 T064–T070延期；T071–T083验收责任保留。Dashboard/Analytics是轻量受权数据展示，不扩展独立BI、实时执行基础设施或支付系统。
