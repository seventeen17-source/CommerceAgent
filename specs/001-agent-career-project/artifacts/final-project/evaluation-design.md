# ProcurePilot Evaluation Design

## Dataset target

Create **60 versioned cases** for the core implementation. Use `dev` for iteration and a frozen `test` split for final evidence. Business state must be resettable from fixtures before each case.

| Category | Cases | Purpose |
|---|---:|---|
| Happy-path procurement | 12 | end-to-end task success across categories/constraints |
| Missing/ambiguous requirements | 6 | clarification and safe defaults |
| Tool selection | 7 | next-action/tool choice under different evidence needs |
| Tool parameter validation | 5 | IDs, quantity, dates, cost center, quote freshness |
| Budget/policy constraints | 6 | deterministic blocks and retrieval-grounded policy |
| Approval/HITL | 4 | threshold/risk-based escalation |
| Timeout/retry | 4 | bounded read retry and termination |
| Duplicate/idempotency | 4 | repeated writes and unknown outcomes |
| Prompt injection/authorization | 5 | untrusted supplier/policy text, denied writes |
| Partial failure/verification | 3 | write succeeded/response lost, verify-after-write |
| Retrieval/citation | 4 | policy recall, version and citation correctness |
| **Total** | **60** | |

Recommended split: 40 dev / 20 frozen test. The exact split is versioned before optimization and test answers remain unavailable during tuning.

## Evaluation case schema

Each case records:
- `case_id`
- `dataset_version`
- `dataset_split` = dev/test
- `category`
- `user_task`
- `initial_business_state_fixture`
- `user_identity_and_permissions`
- `allowed_tools`
- `expected_call_predicates`
- `forbidden_actions`
- `expected_business_state_predicates`
- `expected_answer_facts`
- `citation_expectation`
- `max_steps`
- `retry_budget`
- `token_budget`
- `latency_budget`
- `scorers`
- `tags`

Expected calls should use predicates when multiple valid trajectories exist. Do not force one exact chain-of-thought or one exact supplier when several choices satisfy all hard constraints.

## Metrics

### 1. Task Success Rate
`successful_cases / attempted_cases`

A case succeeds only when required business-state predicates, answer facts, and safety constraints all pass.

### 2. Tool Selection Accuracy
Evaluate whether the set/order constraints for necessary tools were satisfied and forbidden/unnecessary high-risk tools were avoided. Use predicate scoring rather than exact-trace equality when several valid paths exist.

### 3. Tool Parameter Accuracy
`valid_expected_parameters / evaluated_parameters`, with critical parameters such as IDs, quantity, dates, amount and idempotency key separately reported.

### 4. Policy Compliance Rate
`policy_compliant_cases / policy_cases`. Any hard policy violation is a case failure.

### 5. Unsafe Action Rate
`unsafe_effective_actions / safety_cases`. Target for final core is **0 effective unsafe writes**; blocked attempts are recorded separately and not hidden.

### 6. Retrieval Recall
For retrieval cases, whether at least one gold-relevant policy passage/version appears in the retrieved candidate set.

### 7. Citation Accuracy
Whether claims about policy thresholds/rules cite a passage that actually supports the claim and is valid for the scenario date/version.

### 8. Average Tool Calls
Report mean plus distribution; lower is not automatically better if fewer calls reduce correctness.

### 9. End-to-End Latency
Report median and p95, including retries. Also report model latency and tool latency when possible.

### 10. Token Cost
Report input/output tokens and estimated cost per successful task, with model/config/version recorded.

Additional useful metrics:
- clarification precision/recall on cases with missing blocking fields;
- duplicate effective-write rate;
- bounded-retry compliance;
- approval routing accuracy;
- run completion / max-step termination rate.

## Baseline → V1 → Optimized experiment

### Baseline
A simple single-prompt/tool-calling loop with the same model, tool permissions, business fixtures and budgets. It may have minimal orchestration but must still be prevented from unsafe server-side writes.

### Version 1
Explicit state graph, normalized task state, precondition checks, typed tools, bounded retries, policy retrieval/citations, HITL and trace.

### Optimized Version
After V1 dev-set error analysis, choose **one largest attributable error category** and make one targeted improvement (for example retrieval fusion, tool-selection routing, better missing-field policy or parameter schema). Do not simultaneously change model, tool set and prompt if attribution matters.

## Comparability controls

For a valid Baseline/V1/Optimized comparison:
- same dataset version and split;
- same business fixtures;
- same tool permission set;
- same model/provider/version unless every compared system is rerun;
- same retry/max-step/token budgets;
- same metric formulas;
- same scorer versions.

If an environment/model changes and all versions cannot be rerun, mark results incomparable rather than reporting an “improvement.”

## Leakage controls

- Dev cases may guide changes.
- Frozen test expected outputs/oracles are not inspected during tuning.
- Any case removal/exclusion must be recorded before looking at aggregate final test results unless the case is objectively invalid.
- Do not select only successful random runs; stochastic systems should be repeated where budget permits.

## Scoring priority

1. Deterministic business-state and safety checks.
2. Deterministic tool/parameter predicates.
3. Deterministic citation/source checks.
4. Rule-based answer-fact extraction where possible.
5. Model judge only for genuinely qualitative explanation quality; judge version/prompt must be frozen and a human sample audited.

## Evidence ledger for future resume claims

Any measured claim must store:
- run ID(s);
- code/commit version;
- dataset version/hash;
- sample count and denominator;
- model/config;
- tool-contract version;
- metric formula;
- retries/token/latency budget;
- raw case results;
- reproduction command;
- limitations.

Before implementation, all numeric performance values remain targets, never achievements.
