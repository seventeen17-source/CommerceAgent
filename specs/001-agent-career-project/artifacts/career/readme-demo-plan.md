# ProcurePilot README + Demo Plan

## README structure

1. **What problem does ProcurePilot solve?**
   - one-paragraph enterprise procurement problem;
   - why a normal chatbot is insufficient;
   - why deterministic rules alone do not handle ambiguous/multi-step evidence selection.

2. **What the Agent is allowed to decide**
   - missing-information detection;
   - next evidence/tool choice;
   - comparison among deterministically acceptable options;
   - escalation/approval decision request.

3. **What the Agent is NOT allowed to decide**
   - permissions;
   - budget truth;
   - supplier certification truth;
   - transaction validity;
   - approval outcome;
   - raw database writes.

4. **Architecture**
   - minimal UI → Python Agent service → typed Tool/API → Java backend → PostgreSQL;
   - policy retrieval and evaluation/trace as cross-cutting capabilities.

5. **State workflow**
   - graph diagram from normalize/clarify through verify result.

6. **Tool contracts**
   - summarize 8 tools and their risk/write/idempotency properties.

7. **Business/domain model**
   - supplier, quote, budget, request, approval, PO draft, audit.

8. **Reliability and security**
   - bounded retry;
   - idempotency;
   - verify-after-write;
   - Prompt Injection boundary;
   - authorization and HITL.

9. **Evaluation**
   - dataset version/split;
   - Baseline/V1/Optimized;
   - deterministic scorers and metrics;
   - measured results only after reproducible runs exist.

10. **Quickstart**
    - Docker Compose startup;
    - fixture reset;
    - one demo request;
    - run eval command;
    - inspect run trace.

11. **Limitations / honest boundaries**
    - local/synthetic business system unless real adapter is connected;
    - one procurement category/workflow;
    - no claim of production ERP integration;
    - no Multi-Agent/K8s by default;
    - performance values tied to a specific dataset/model/config.

12. **Design decisions / rejected complexity**
    - why structured facts are not RAG;
    - why MCP is Should, Multi-Agent/K8s Reject;
    - why business rules live outside the model.

## 60–90 second demo script

### 0–10s — Problem and architecture
“ProcurePilot不是采购聊天机器人。它把一个不完整采购需求，通过受控 Tool 调用连接到供应商、报价、预算和审批系统；LLM 负责不确定判断，真正的权限、金额、状态转换和写入由业务后端保证。”

Show architecture diagram briefly.

### 10–40s — Happy path
Input a complete request.

Show:
1. Agent state identifies needed evidence.
2. `supplier_search`, `quote_query`, `budget_check` calls appear in trace.
3. acceptable supplier/quote set is shown.
4. `create_purchase_request` creates exactly one persistent request.
5. final answer shows verified request ID/status and evidence.

Avoid narrating every UI click; focus on business-state change and Tool evidence.

### 40–65s — Controlled failure / safety
Run one of:
- high-value request → approval required, PO tool blocked;
- Prompt Injection in supplier/policy content → unsafe instruction ignored and server-side guard blocks forbidden write;
- duplicate submission → same effective request due to idempotency.

Show trace/event explaining the deterministic reason, not hidden chain-of-thought.

### 65–80s — Evaluation evidence
Show evaluation summary tied to dataset version and run config:
- task success;
- safety/unsafe write count;
- one failure taxonomy example;
- latency/tool-call/cost view if measured.

If implementation has not run, this portion must display the **planned evaluation design**, not invented results.

### 80–90s — Closing
“这个项目重点不是堆 Agent 组件，而是把真实业务状态、Tool 安全、失败恢复、离线评估和可观测性做成一个可以复现的闭环。”

## Demo evidence checklist

- architecture diagram;
- one happy-path run ID;
- one controlled failure/safety run ID;
- database/business-state proof before/after;
- tool trace with redacted args/results;
- evaluation dataset/run version;
- explicit local/synthetic-system disclosure.
