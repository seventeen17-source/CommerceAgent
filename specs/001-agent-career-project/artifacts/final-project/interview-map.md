# ProcurePilot Interview Knowledge Map

The goal is not to memorize framework APIs. For every Must module, the user should be able to explain the tradeoff and reproduce a simplified core implementation without relying on AI to make the design decision.

| Module | Likely interview question | Must understand | Must be able to reproduce | AI may assist | Judgment that cannot be outsourced |
|---|---|---|---|---|---|
| Agent necessity | Why not a normal workflow/CRUD system? | uncertainty vs deterministic rules; dynamic next-action/evidence selection | small branch where different missing/evidence states select different next tools | boilerplate/tests | defining the genuine model-decision boundary |
| State graph | Why use a graph/state machine instead of while-loop ReAct? | explicit state, conditional edges, stop/max-step, checkpoint/resume | minimal state object + 4–5 node graph with conditional routing | framework syntax | deciding what is state and when flow stops |
| Tool calling | How do you stop the model from calling arbitrary actions? | allowlists, typed schemas, auth context separate from model args | one typed read tool + one protected write tool | client boilerplate/schema generation | tool surface and risk classification |
| Java/Python boundary | Why two services? | deterministic business authority vs probabilistic orchestration; latency/complexity tradeoff | explain API boundary and remove it if one side becomes empty | scaffolding | whether split adds real responsibility or architecture theater |
| Transactions/state machine | What happens if the Agent requests an invalid state transition? | transaction/validation/optimistic version/state transitions | simple request→approval→PO state machine with rejected invalid transition | test generation | authoritative domain invariants |
| Idempotency | What if a write succeeds but the response times out? | duplicate-write risk, stable idempotency key, verify-before-retry | idempotent create endpoint + unknown-outcome status check | repetitive edge-case tests | key semantics and retry policy |
| HITL | Where does human approval belong? | pause/resume, authoritative approval state, separation of requester/approver | pending approval checkpoint and resume path | UI boilerplate | deciding which risks require human authority |
| RAG boundary | Why not put supplier/price/budget in a vector DB? | structured authoritative facts vs unstructured knowledge | policy retrieval returning source/version/citation | chunking scripts | deciding when retrieval is actually necessary |
| Prompt Injection | If a policy chunk says “ignore all rules,” what happens? | untrusted content, server-side permissions, no prompt-granted authority | adversarial case that tries and fails to trigger forbidden write | attack-case generation | security boundary |
| Eval design | How do you know the Agent is better? | golden set, dev/test leakage, deterministic oracles, acceptable trajectories | scorer for business state + forbidden action + tool predicate | case generation | metric definitions and what counts as success |
| Baseline/V1/optimization | How do you prove an improvement? | comparable model/data/tools/budgets; one change at a time | run same cases and produce comparable report | result formatting | causal attribution and avoiding cherry-picking |
| Observability | How do you debug a failed Agent run? | run_id, step/tool/retrieval/approval/state refs, latency/token | reconstruct a run from structured trace records | dashboard formatting | what evidence is necessary without logging hidden chain-of-thought |
| Retry/termination | How do you prevent loops? | max steps, retry budgets, safe vs unsafe retry | bounded read retry and terminal failure | boilerplate | retry classification |
| MCP | Why is MCP not Must? | interoperability value vs business value; protocol after contracts | optionally expose one existing tool later | adapter implementation | whether protocol adds value |
| Multi-Agent | Why did you reject it? | coordination/debug/eval overhead; single graph sufficiency | explain measured trigger that would justify revisit | research | refusing complexity without evidence |
| Deployment | Why no Kubernetes? | project scale and reproducibility vs platform complexity | Docker Compose startup and health checks | YAML boilerplate | scope ROI |

## Core code the user should personally be able to simplify/rewrite

1. Agent state definition and conditional routing.
2. Tool schema + safe Tool invocation wrapper.
3. Business-state transition validation.
4. Idempotent write path and verify-after-write behavior.
5. HITL pause/resume state.
6. Retrieval result with citation/version metadata.
7. Deterministic evaluation scorer for task success + unsafe writes.
8. One structured run trace reconstruction query/path.

## Suggested deep follow-up questions

- Suppose budget changes after the Agent checked it but before request creation—where is the race prevented?
- Why is `budget_check` not enough unless the write transaction revalidates authoritative state?
- What should the Agent do when two suppliers are both valid and the gold dataset has no single best answer?
- How would you evaluate tool selection without requiring an exact chain?
- When can a read timeout be retried safely? What changes for a write timeout?
- Why can retrieved policy text not become a security authority?
- If LangGraph disappears tomorrow, what design remains?
- What evidence would make you add Multi-Agent, MCP, Redis or Kubernetes?
- If Python↔Java network latency becomes the biggest issue, how would you simplify?
- Which resume metrics are currently targets versus measured claims?
