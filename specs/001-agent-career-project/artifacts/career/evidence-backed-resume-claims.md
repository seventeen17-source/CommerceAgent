# Evidence-Backed Resume Claim Ledger

Only `approved` claims may be stated as achieved results. Before implementation, every performance/result claim remains `target`.

| claim_id | text | status | evaluation_run_refs | dataset_version | metric_definition | limitations | reviewed_at |
|---|---|---|---|---|---|---|---|
| RC001 | 设计企业采购执行 Agent，将不完整需求转化为受预算、政策、权限与审批约束的可执行采购流程 | target |  |  | qualitative design claim | Must be implemented end-to-end before changing to measured/approved |  |
| RC002 | 构建显式状态工作流并通过 Tool/API 连接供应商、报价、预算、采购申请和审批业务状态 | target |  |  | implementation presence + integration acceptance | Requires implemented services/tools and reproducible demo |  |
| RC003 | 通过服务端权限、状态机、幂等和 verify-after-write 约束高风险 Agent 写操作 | target |  |  | safety acceptance tests + duplicate effective-write metric | Requires security/idempotency test evidence |  |
| RC004 | 在版本化离线评估集上达到任务成功率 `[待实测]` | target |  | planned-60-case-v1 | successful_cases / attempted_cases | Model/config/tool budgets must be recorded; no number before run |  |
| RC005 | 不安全有效写入率为 `[待实测]` | target |  | planned-60-case-v1 | unsafe_effective_actions / safety_cases | Final acceptance target is zero but target is not an achieved result |  |
| RC006 | 将 Baseline 任务成功率从 `[待实测]` 提升至 `[待实测]` | target |  | planned-60-case-v1 | same-dataset comparable Baseline vs Optimized | Both systems must use comparable model/tools/budgets; no cherry-picking |  |
| RC007 | 政策检索 Recall@K / 引用正确率达到 `[待实测]` | target |  | planned-60-case-v1 | evaluation-design.md definitions | Only applicable if RAG remains in final implementation |  |
| RC008 | p50/p95 端到端时延为 `[待实测]`，平均每任务 Tool 调用 `[待实测]`，Token 成本 `[待实测]` | target |  | planned-60-case-v1 | evaluation-design.md definitions | Must include retry policy and exact model/version |  |

## Promotion rules

### `target → measured`
Requires:
- concrete implementation commit/version;
- evaluation run reference;
- dataset version/hash;
- sample count and denominator;
- model/config and tool-contract version;
- metric formula;
- raw result artifact;
- known limitations.

### `measured → approved`
Requires:
- reproduction or review of the run;
- no known leakage/cherry-picking issue;
- wording matches the metric exactly;
- local/synthetic system boundaries are not hidden;
- `reviewed_at` recorded.

## Prohibited resume language before evidence

Do not write:
- “成功率提升 30%”
- “延迟降低 40%”
- “零安全事故”
- “生产级部署”
- “接入企业 ERP/SAP”
- “支持百万级并发”

unless the exact claim is supported by an approved evidence record. The design itself may state acceptance **targets** without turning them into achievements.

## Contract 5 career-output verdict

- Chinese project-experience template: PASS.
- README/demo template: PASS.
- Evidence-backed claim model: PASS.
- Unmeasured numbers remain targets/placeholders: PASS.

**Career-output portion of Contract 5: PASS at design/template stage.**
