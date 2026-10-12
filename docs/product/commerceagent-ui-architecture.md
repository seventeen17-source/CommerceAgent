# CommerceAgent UI Experience Architecture

## Phase 7 — Product Experience Layer

## 1. Purpose

本阶段不是简单增加前端页面，而是将 US5 已完成的 Agent Runtime、安全边界、人机协同能力转化为可展示、可运营、可理解的平台能力。

核心目标：

> 让非技术用户看到服务结果，让运营人员看到 Agent 执行过程，让企业管理者看到 AI 带来的业务价值。

底层仍然是同一个 CommerceAgent 平台，不是三个独立系统。

---

## 2. Product Model

```
                    CommerceAgent

                 Agent Runtime

        ┌────────────┼────────────┐
        │            │            │
     Customer    Operator     Enterprise
      View        View          View

```

三个角色观察同一个售后任务，只是权限和展示维度不同。

---

## 3. Role Experience

## Customer Portal

目标：提出售后请求并查看处理结果。

页面：

- 我的订单
- 发起售后
- 当前处理进度
- AI处理结果
- 历史服务记录

重点展示：

用户不需要理解 Agent，只需要知道问题是否被安全解决。

---

## Operator Workspace

目标：展示 Agent 如何工作。

页面：

- Agent Mission Center
- 待处理任务
- Agent执行轨迹
- 人工接管
- 异常事件
- 历史案例

重点展示：

物流异常 → 规则判断 → 安全校验 → 执行/人工协同

---

## Enterprise Dashboard

目标：展示企业价值。

页面：

- 服务总览
- 自动化率
- 人工介入率
- 风险事件
- Agent能力分析

重点展示：

AI Agent不仅完成任务，同时具备安全边界。

---

## 4. UI Design Principle

禁止设计成传统审批系统：

错误：

申请 → 审批 → 通过

正确：

用户问题 → Agent理解 → Agent决策 → 安全验证 → 执行结果

---

## 5. Frontend Integration Principle

前端优先消费已有 Runtime Contract。

核心对象：

- AgentRun
- RunStatus
- Timeline/Event
- ToolExecution
- VerificationResult
- SafetyEvent

不重新设计业务接口。

---

## 6. Demo Story

一次售后任务贯穿三个视角：

Customer:

提交退款申请

↓

Operator:

查看 Agent 执行过程、安全检查、必要时人工接管

↓

Enterprise:

查看整体运营效果和安全指标
