# CommerceAgent UI Design Handoff

## Current Stage

Phase 7 — Product Experience Layer

## Background

US5 已完成安全失败处理、人工升级、安全评估等 Agent Runtime 能力。

本阶段负责将已有能力产品化展示。

---

# Required Reading

开发前必须阅读：

- PROJECT_PROGRESS.md
- AGENTS.md
- specs/002-commerce-after-sales-agent/
- contracts/
- agent-service/app/api/
- agent-service/app/agent/

---

# UI Goal

不是制作普通管理后台。

需要体现：

1. Agent如何理解问题
2. Agent如何执行任务
3. Agent如何保证安全
4. 企业如何获得价值

---

# Main Views

## Customer View

关键词：Result

看到：

- 售后申请
- 当前状态
- AI处理结果
- 服务记录

---

## Agent Operator View

关键词：Process

看到：

- 当前Run
- Node执行链
- Tool调用
- Verification
- Human escalation

---

## Enterprise View

关键词：Value

看到：

- 业务指标
- 自动化率
- 风险事件
- Agent效果

---

# API Alignment

禁止前端创造新的业务模型。

优先使用：

- /runs
- /input
- /resume
- events
- tool execution trace

新增展示接口必须保持现有命名风格。

---

# Implementation Order

UX001 信息架构

UX002 登录与RBAC

UX003 Customer Portal

UX004 Agent Mission Center

UX005 Enterprise Dashboard

UX006 API Contract

---

# Design Reminder

不要做：

审批按钮系统。

要做：

AI Agent工作过程展示平台。
