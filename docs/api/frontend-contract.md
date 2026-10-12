# Frontend API Contract

## Principle

Frontend is a presentation layer of CommerceAgent Runtime.

Do not duplicate business rules.

Business truth remains in:

- commerce-backend
- agent-service

---

# Existing Runtime APIs

## Create Run

POST /runs

Purpose:

创建一次 Agent 执行。

---

## User Input

POST /runs/{runId}/input

Purpose:

用户补充信息。

---

## Resume

POST /runs/{runId}/resume

Purpose:

恢复等待中的 Agent Run。

---

# UI Required Read Models

## Dashboard Overview

GET /api/v1/dashboard/overview

展示：

- total runs
- completed runs
- escalated runs
- safety stops

---

## Run Timeline

GET /api/v1/runs/{runId}/timeline

展示：

- node
- status
- evidence
- verification

---

## Safety Events

GET /api/v1/safety/events

展示：

- SAFE_STOP
- FAILED
- ESCALATED

---

# Naming Rule

沿用现有 REST 风格：

资源名复数

/api/v1/{resource}

禁止出现：

/taskPage
/getAgentData

等前端导向命名。
