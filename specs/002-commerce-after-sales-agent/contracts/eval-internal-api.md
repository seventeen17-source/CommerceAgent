# Eval Internal API Contract

该契约只用于确定性、本地/离线评测，不属于公开 Customer API 或 Agent API。

## 可用范围

该 endpoint 只能在 Java Backend 运行于 `test` 或 `eval` profile 时存在。

在普通 `dev` 或 production-like profile 下必须完全不注册。

## Reset Fixture

```text
POST /internal/eval/fixtures/{caseId}/reset
```

用途：把权威 commerce state 重置到某个版本化 Eval Case 对应的确定性初始状态。

### Request

Path：
- `caseId`：稳定 Eval Case 标识，必须存在于版本化 dataset manifest。

可选 Body：

```json
{
  "datasetVersion": "v1"
}
```

### Success Response

```json
{
  "caseId": "refund-logistics-001",
  "datasetVersion": "v1",
  "fixtureVersion": "sha-or-version",
  "resetAt": "2026-09-15T12:00:00Z"
}
```

### Rules

- 同一个 `caseId + datasetVersion` 的 reset 必须确定性。
- Reset 必须清除/重建会影响 scorer 的前序业务对象，包括 refunds、returns、support tickets、approvals、idempotency records 和必要的 audit/test state。
- Reset 必须 seed Eval Case 所要求的精确 User/Order/Shipment/LogisticsEvent/AfterSalesRule 状态。
- Agent/LLM 不得把该 endpoint 当作 Tool。
- Eval Runner 在每个 case 执行前 out-of-band 调用它。
- Reset 结果不是 Agent Evidence，也不得进入 Prompt。

### Errors

- `404 EVAL_CASE_NOT_FOUND`：case/version 不存在。
- `409 EVAL_RESET_CONFLICT`：另一个 fixture reset transaction 正在执行。
- `500 EVAL_RESET_FAILED`：确定性 reset 失败；此 case 必须标记为 infrastructure failure，而不是 model failure。

## Ownership

Java Backend 拥有该 endpoint，因为它拥有权威 commerce state。

Dataset Definition 保存在 `eval/datasets/` 的版本化文件中；endpoint 只接收稳定 case id/version，并应用 test/eval profile 下实现的 fixture mapping。
