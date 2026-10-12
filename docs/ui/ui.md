# CommerceAgent UI Design Handoff

## Current Stage

Phase 7 — Product Experience Layer

Branch:

feat/ui-experience-layer

---

# 1. Purpose

本文档用于指导后续 Agent / 前端开发人员实现 CommerceAgent Web 产品体验层。

目标不是制作普通后台，而是将 US1-US5 已完成能力展示出来：

- Agent Runtime
- Run execution
- Tool usage
- Verification
- Safety Boundary
- Human Escalation

---

# 2. Required Reading

开发前必须阅读：

- AGENTS.md
- PROJECT_PROGRESS.md
- specs/002-commerce-after-sales-agent/
- contracts/
- agent-service/app/api/
- agent-service/app/agent/

---

# 3. Product Model

CommerceAgent 是一个统一 Web 平台。

不是三个系统。

根据账号权限显示不同视角。

```
                 CommerceAgent

                  Agent Runtime

        ┌────────────┼────────────┐
        │            │            │
    Customer    Operator    Enterprise
      View        View         View
```

---

# 4. Core Screens

## Screen 01 Login

目标：

统一入口，根据角色进入不同 Workspace。

角色：

- customer
- operator
- enterprise

---

## Screen 02 Customer Portal

目标：

模拟真实售后入口。

展示：

- 我的订单
- 发起售后
- 当前处理状态
- 最终结果

不展示：

- Agent内部Trace
- Runtime细节

---

## Screen 03 Agent Mission Center

核心展示页面。

展示：

- 当前任务
- Run状态
- Agent执行流程
- 处理结果

数据来源：

- Run
- Event
- ToolExecution

---

## Screen 04 Run Replay

展示一次任务完整生命周期：

START
↓
Intent
↓
Tool Call
↓
Business Rule Check
↓
Safety Guard
↓
Decision
↓
Verification

重点：

展示 Agent 为什么这样处理。

---

## Screen 05 Safety Center

展示 CommerceAgent 核心差异。

展示：

- SAFE_STOP
- ESCALATED
- FAILED
- Boundary Protection

目标：

证明 Agent 不会越权执行。

---

## Screen 06 Enterprise Dashboard

展示企业价值。

展示：

- 请求数量
- 自动完成率
- 人工介入率
- 风险拦截
- 服务效率

---

## Screen 07 Human Collaboration

不是审批页面。

展示：

Agent无法安全完成任务时：

- 原因
- 证据
- 建议
- 人工接管

---

# 5. API Alignment

前端禁止重新创造业务模型。

优先复用：

- /runs
- /input
- /resume
- events
- tool execution trace
- verification result

新增接口必须保持已有命名风格。

---

# 6. Implementation Order

UX001 信息架构

UX002 RBAC

UX003 Customer Portal

UX004 Agent Mission Center

UX005 Run Replay

UX006 Safety Center

UX007 Enterprise Dashboard

UX008 Human Collaboration

---

# 7. Design Principle

禁止：

- 普通审批后台
- CRUD管理系统
- 手机App设计

目标：

打造企业级 AI Agent 工作展示平台。

核心表达：

用户提出问题 → Agent处理 → 安全判断 → 结果验证 → 企业获得价值。
