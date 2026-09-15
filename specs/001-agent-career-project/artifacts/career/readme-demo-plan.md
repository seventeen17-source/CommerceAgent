# CommerceAgent README & Demo Plan

## README structure

1. **Problem** — after-sales requests require repeated cross-system checks across order, logistics, policy and refund/return systems.
2. **Why Agent** — next evidence/tool/action depends on ambiguous intent and intermediate results; deterministic backend still controls authority.
3. **Architecture** — UI → Python Agent → Tool Adapter → Java After-sales Backend → PostgreSQL, plus policy retrieval and Trace/Eval.
4. **Agent workflow** — explicit state graph from request parsing to evidence gathering, eligibility, approval, write and verification.
5. **Business backend** — order ownership, eligibility, amount, transactions, state machine, idempotency and audit.
6. **Tools** — order/logistics/policy/eligibility/refund/return/ticket/approval/status contracts.
7. **Safety** — Prompt Injection, cross-user access, high-risk approval, write timeout and duplicate-write protection.
8. **Evaluation** — 60–80 versioned cases, Baseline/V1/Optimized and deterministic business-state oracles.
9. **Observability** — one `run_id` reconstructs state/tool/retry/approval/write/verification path.
10. **Known limitations** — synthetic/local business systems; no claim of real payment/ERP production integration.
11. **Quickstart** — reproducible local run.
12. **Results** — only actual measured metrics with dataset/run/config references.

## 60–90 second demo script

### 0–10s: problem
Show a customer request:

> “我 9 月 10 日买的耳机到现在还没收到，我不要了，帮我退款。”

Explain: the system must do more than answer how to refund; it must complete a safe after-sales workflow.

### 10–35s: dynamic evidence and tools
Show trace/state:
- resolve order;
- query order state;
- query logistics;
- retrieve policy if needed;
- call deterministic eligibility service.

Highlight that the Agent chooses what evidence is needed next; the Java backend decides whether a refund/return is actually allowed.

### 35–50s: business action
Show eligible ordinary refund:
- validated amount;
- idempotency key;
- `create_refund_request`;
- post-write `get_after_sales_status` verification.

### 50–65s: failure/safety path
Switch to one of:
- high-value refund → `WAITING_APPROVAL`;
- fake-admin Prompt Injection → denied;
- refund API timeout → status recovery, no duplicate refund.

### 65–80s: Eval / Trace
Show one run trace and the eval table/categories. If real metrics exist, show them with dataset/run ids. Otherwise label all numbers as targets.

### 80–90s: takeaway
One sentence:

> CommerceAgent uses the LLM for ambiguity resolution and dynamic Tool orchestration, while deterministic backend services retain control over money, permissions and state changes.

## Demo evidence to capture later
- architecture diagram;
- normal refund trace;
- return path trace;
- HITL screenshot/state;
- Prompt Injection denial;
- timeout/idempotency recovery;
- actual eval summary;
- dataset version and run config.

## Honesty boundary
The demo must state that order/logistics/refund systems use synthetic or locally implemented enterprise semantics unless a real external integration is actually connected. Do not describe local mocks as production platform integration.