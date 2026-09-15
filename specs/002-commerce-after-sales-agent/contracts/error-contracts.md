# CommerceAgent Error Contracts

Errors are stable machine-readable signals. The Agent must branch on error semantics rather than parsing natural-language messages.

## Standard error envelope

```json
{
  "errorCode": "ORDER_FORBIDDEN",
  "message": "Order is not accessible to the authenticated user",
  "retryable": false,
  "traceId": "...",
  "details": {}
}
```

## Error taxonomy

| Code | Meaning | Retryable | Agent handling |
|---|---|---:|---|
| `AUTH_REQUIRED` | Missing/invalid authentication | No | stop; request valid session |
| `ORDER_NOT_FOUND` | Order does not exist | No | clarify/search user's orders or stop |
| `ORDER_FORBIDDEN` | Order belongs to another user / access denied | No | safe stop; never reveal order details |
| `AMBIGUOUS_ORDER` | More than one plausible target remains | No | ask user clarification; no write |
| `INVALID_ORDER_STATE` | Requested after-sales action incompatible with current order state | No | re-evaluate path; do not force write |
| `LOGISTICS_UNAVAILABLE` | Logistics dependency unavailable | Yes, bounded | retry within budget, then escalate/safe stop |
| `POLICY_NOT_FOUND` | No suitable policy evidence | No/conditional | continue only if deterministic rule is sufficient; otherwise escalate |
| `POLICY_VERSION_CONFLICT` | Effective policy version cannot be resolved | No | safe stop/manual review; do not choose arbitrary text |
| `ELIGIBILITY_DENIED` | Deterministic rules deny action | No | explain denial; no write |
| `MANUAL_REVIEW_REQUIRED` | Deterministic rules require human handling | No | create support ticket / escalate |
| `APPROVAL_REQUIRED` | Action is eligible but requires approval | No | create/wait for approval; no business write yet |
| `APPROVAL_DENIED` | Human approval denied | No | stop proposed write; report outcome |
| `APPROVAL_EXPIRED` | Approval no longer valid | No | request new approval only if still appropriate |
| `INVALID_PARAMETER` | Tool/API argument failed schema/business validation | No | correct parameter from authoritative evidence or safe stop |
| `AMOUNT_EXCEEDS_ALLOWED` | Requested amount exceeds server-calculated bound | No | never retry with guessed amount; use authoritative amount |
| `IDEMPOTENCY_CONFLICT` | Same key reused with conflicting payload | No | stop and inspect existing logical action |
| `DUPLICATE_AFTER_SALES` | Conflicting refund/return already exists | No | query existing after-sales state and report/route accordingly |
| `WRITE_TIMEOUT_UNKNOWN` | Write call timed out and commit outcome is unknown | No direct retry | call `get_after_sales_status`; reuse same key only after authoritative recovery |
| `DEPENDENCY_TIMEOUT` | Read/decision dependency timed out | Yes, bounded | retry within operation policy, then safe stop/escalate |
| `DEPENDENCY_UNAVAILABLE` | Required service unavailable | Yes, bounded | retry then safe stop/escalate |
| `TOOL_NOT_ALLOWED` | Model attempted unregistered/disallowed capability | No | block action; mark safety/tool-selection failure |
| `MAX_STEPS_EXCEEDED` | Agent exhausted bounded step budget | No | safe stop/escalate; never continue loop |
| `REPEATED_NO_PROGRESS` | Same tool/arguments repeated without new evidence | No | circuit-break and safe stop/escalate |
| `POST_WRITE_VERIFICATION_FAILED` | Write reported success but final state could not be verified | No blind retry | query authoritative state; mark partial/unknown and escalate if unresolved |
| `PROMPT_INJECTION_BLOCKED` | Request/retrieval content attempted to alter protected policy/authority | No | continue only under normal permissions or safe stop |
| `INTERNAL_ERROR` | Unclassified internal failure | Conditional | no unsafe continuation; record trace and fail safely |

## Handling rules

1. `retryable=true` never means unlimited retry; each tool has a bounded retry budget.
2. Write errors are more conservative than read errors. `WRITE_TIMEOUT_UNKNOWN` must never be translated into an automatic new write.
3. Authorization and eligibility errors are terminal for that proposed action unless authoritative business state later changes.
4. Prompt text cannot transform a non-retryable/forbidden error into an allowed action.
5. Error codes are included in ToolExecution/AgentRun trace and eval failure taxonomy.
6. UI may localize human-readable messages, but code branches only on stable error codes/status fields.
