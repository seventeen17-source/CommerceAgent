# Red-Team Resolution — CommerceAgent

## Final dispositions

| Issue | Severity | Disposition | Result |
|---|---|---|---|
| Fixed intent→refund router | P0 | validate | Week 2 must prove evidence-dependent branching across refund/return/clarification/approval/escalation |
| FAQ/chatbot-only behavior | P0 | reject behavior | Core demo requires a real business-state change or deliberate safe refusal/escalation |
| RAG authorizes money | P0 | delete design | RAG is policy evidence only; deterministic eligibility controls action/amount |
| Cross-user order access | P0 | server-side block | Backend checks authenticated ownership on every read/write |
| Duplicate refund after timeout | P0 | idempotency + recovery | Stable idempotency key and status check before reissue |
| High-risk autonomous refund | P1 | HITL | `WAITING_APPROVAL`; Agent cannot self-approve |
| Open-ended Agent loop | P1 | bound | Explicit state graph, max steps, repeat-call breaker, safe stop |
| Java/Python architecture theater | P1 | validate boundary | Java must own substantial domain/transaction logic; Python must own real Agent orchestration/eval |
| Synthetic system looks fake | P1 | strengthen semantics | Persistent contract-realistic order/logistics/after-sales state; honest README boundary |
| Scope expansion to full customer service | P1 | delete breadth | v1 only order/logistics/refund/return/escalation |
| MCP/Multi-Agent/K8s keyword stuffing | P2 | downgrade/reject | MCP optional after core; Multi-Agent/K8s rejected by default |

## P0 status

All P0 issues have an explicit implementation control or validation gate. No unresolved P0 remains at design time.

## Final decision

CommerceAgent remains selected only while the implementation preserves this boundary:

> Agent decides what evidence/tool/path is needed next; deterministic business services decide whether the requested state-changing action is legal.

If that boundary disappears, reopen project selection instead of compensating with more technology.