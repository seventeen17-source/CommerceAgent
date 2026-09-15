# Eval Internal API Contract

This contract exists only for deterministic local/offline evaluation. It is not part of the public customer or Agent API surface.

## Availability

The endpoint MUST exist only when the Java backend runs with `test` or `eval` profile.

In normal/dev/production-like profiles it MUST NOT be registered.

## Reset fixture

```text
POST /internal/eval/fixtures/{caseId}/reset
```

Purpose: reset authoritative commerce state to the deterministic starting state associated with one versioned eval case.

### Request

Path:
- `caseId`: stable eval case identifier that exists in the versioned dataset manifest.

Optional body:

```json
{
  "datasetVersion": "v1"
}
```

### Success response

```json
{
  "caseId": "refund-logistics-001",
  "datasetVersion": "v1",
  "fixtureVersion": "sha-or-version",
  "resetAt": "2026-09-15T12:00:00Z"
}
```

### Rules

- Reset MUST be deterministic for the same case/dataset version.
- Reset MUST clear or recreate all business objects whose prior execution could affect scoring, including refunds, returns, support tickets, approvals, idempotency records, and relevant audit/test state.
- Reset MUST seed the exact User/Order/Shipment/LogisticsEvent/AfterSalesRule state required by the eval case.
- The Agent/LLM MUST NOT be allowed to call this endpoint as a tool.
- The eval runner calls it out-of-band before executing each case.
- Reset is never evidence for the Agent and is never included in prompts.

### Errors

- `404 EVAL_CASE_NOT_FOUND`: case id/version does not exist.
- `409 EVAL_RESET_CONFLICT`: reset cannot complete because a fixture transaction is already in progress.
- `500 EVAL_RESET_FAILED`: deterministic reset failed; the eval case MUST be marked infrastructure failure rather than model failure.

## Ownership

The Java backend owns this endpoint because it owns authoritative commerce state. Dataset definitions remain versioned files under `eval/datasets/`; the endpoint receives only a stable case id/version and applies the corresponding fixture mapping implemented for eval/test profiles.
