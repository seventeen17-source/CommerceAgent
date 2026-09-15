# Red Team — Developer Elimination Memo

Target: **CommerceAgent — E-commerce After-sales Execution & Exception Handling Agent**.

| issue | severity | attack | required treatment |
|---|---|---|---|
| Write timeout can duplicate money/state changes | P0 | Retrying a timed-out refund blindly can create duplicate business objects | Stable idempotency key, ambiguous-completion status query, same-key retry only when safe |
| Model may access another user's order | P0 | Prompt-provided order id cannot be trusted | Backend rechecks authenticated ownership on every read/write |
| RAG/prompt injection can try to override policy | P0 | Retrieved/user text may contain malicious instructions | Treat all text as data; backend authorization/eligibility remains authoritative |
| Dynamic Agent loop can run forever or repeat tools | P1 | Open-ended ReAct is hard to debug and control | Explicit state graph, max steps, repeated-call breaker, bounded retry and safe stop |
| Java/Python split can create operational noise | P1 | Two services are unnecessary if either side is a shell | Keep only if both have substantial independent responsibilities; otherwise collapse |
| Eval can become prose judging | P1 | Natural-language answers are subjective | Score tool predicates, parameters, forbidden actions and final backend state deterministically where possible |
| Real e-commerce/payment integration can derail schedule | P2 | OAuth/payment/provider behavior adds little to the core thesis | Use contract-realistic local systems; external adapters are optional after core passes |
| Too many technologies can hide reliability bugs | P2 | MCP, Kafka, Redis, K8s, Multi-Agent increase failure surface | Cut from core unless measured need appears |

## Verdict

**PASS with strict engineering constraints.** The hardest technical proof is not model prompting; it is safe state-changing execution under timeouts, authorization, idempotency, partial failures and traceable recovery. Those mechanisms are Must, not polish.