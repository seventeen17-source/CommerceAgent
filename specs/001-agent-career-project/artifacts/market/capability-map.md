# Evidence-Backed Capability Map

**Snapshot date**: 2026-09-15  
**Core evidence**: `job-postings.csv` (30 deduplicated early-career postings; 20 employers; A/C sources only)  
**Coding detail**: `capability-signals.csv`  
**Audit**: `source-audit.md`

## 1. What the market is actually asking application engineers to do

The strongest cross-employer signal is not “use a particular Agent framework.” It is to turn a model into a reliable task-execution system:

`business request → state/context → planning/workflow → Tool/API → deterministic business system → validation/result`

Across the core sample, employers repeatedly ask engineers to connect LLMs to tools and existing systems, manage multi-step state/context, ground knowledge where needed, evaluate failures, and make the resulting service stable enough to use. Framework names vary; the engineering responsibilities are much more stable.

## 2. Capability priorities

| Capability | Coded signal | Confidence | 6–8 week learning priority | Project implication |
|---|---:|---|---|---|
| Programming + backend engineering | 19 hard-requirement codings; 17 responsibility codings | High | **Core** | Keep a real backend/service layer; language may be Java/Python/Go/C++ depending on role, so existing Java strength remains valuable |
| Tool/API/Function Calling | 18 responsibility codings | High | **Core** | Project must have real tools and observable business-system interaction, not only chat |
| Planning/workflow/state/context | 16 responsibility codings | High | **Core** | Build an explicit stateful task flow with conditions, stop rules and controlled retries |
| RAG/knowledge retrieval | 19 responsibility codings | High | **Core or Should, scenario-dependent** | Use for unstructured policies/knowledge; do not replace authoritative SQL/API facts with vectors |
| Eval/testing/observability | 13 responsibility codings | High | **Core** | Versioned eval cases, failure categories, traces, latency/token/tool-call metrics materially improve hiring evidence |
| Business-system integration | 12 responsibility codings | High | **Core** | Connect to contract-realistic business data/state; a truthful local enterprise simulator is acceptable when production credentials are unavailable |
| Reliability/performance/failure handling | 12 responsibility codings | High | **Core** | Demonstrate timeout, bounded retry, invalid tool/parameter, duplicate call, and failure diagnosis |
| Security/permission/safe writes | 6 responsibility codings | High cross-employer but lower frequency | **Core for any write action** | Permission, validation, approval and audit are mandatory if the Agent changes state |
| MCP/A2A/tool protocols | 6 responsibility codings | High cross-employer | **Should** | Learn and add only when it improves interoperability; first prove tool contracts with a simple callable boundary |
| Multi-Agent | 7 responsibility codings | High cross-employer | **Conditional/Nice** | Do not default to Multi-Agent; keep it only when one stateful workflow cannot credibly solve the task |
| Frontend/HITL interaction | 5 responsibility codings | Medium | **Should** | Minimal UI/task-progress/human intervention is useful; decorative dashboard is not core |
| Containers/cloud/K8s | 3 responsibility codings | Medium | **Understand** | Reproducible containerization is useful; Kubernetes is not a default Must for a solo 6–8 week project |
| Post-training/RL/SFT | mostly preferred/adjacent | Medium | **Defer** | Application-engineering sample does not justify turning this project into a model-training project |
| AI coding workflow | 4 responsibility codings | Medium | **Should** | Use coding agents as productivity tooling while personally owning Agent state, Tool safety, eval and failure handling |

## 3. Role-family differences

### Agent application / AI full-stack
Most strongly values Tool/API execution, workflow/state/context, RAG where justified, business integration, and a visible end-to-end task result. UI breadth is less important than a credible business loop.

### AI backend / Agent framework
Adds stronger expectations around service engineering, async/runtime behavior, routing, stability, performance, traceability, permissions, and standardized tool interfaces. This is where Java/backend experience can differentiate instead of being discarded.

### Eval / quality engineering
Treats evaluation as a first-class engineering system: datasets, deterministic checks, adversarial/safety cases, regression, trace analysis and failure diagnosis. This supports making evaluation part of the portfolio project rather than a final screenshot.

### FDE / enterprise integration
Prioritizes business-process understanding, integration with existing systems, deployability and measurable value. It is strong evidence against building an isolated generic chatbot.

## 4. Company-type differences

- **Large internet / e-commerce**: stronger signals for high concurrency, latency/cost, runtime scale, Tool/RAG reliability and rapid iteration.
- **Cloud / enterprise software**: stronger signals for reusable Agent runtime/framework, tool protocol, platform integration and cross-business reuse.
- **Finance**: stronger signals for evaluation, controlled tools, business data integration, security/permission and explainable operational quality.
- **Traditional manufacturing / industrial software**: strongest evidence that Agent value comes from connecting to ERP/MES/OA/WMS/R&D tools and domain workflows rather than general conversation.
- **AI-native / specialist firms**: more frequent Multi-Agent, advanced workflow, RAG and framework experimentation, but these remain scenario-dependent for a student project.

## 5. High-frequency does not mean “must put it in the project”

### RAG
High-frequency and useful, but only for information that is genuinely retrieval-shaped. Supplier price, inventory, account balance, order state or approval state should remain structured queries/API facts.

### Multi-Agent
Visible across multiple employers but usually one possible architecture rather than a universal screening gate. A well-designed single state graph with Tool calls, failure handling and eval is more credible than unnecessary agent proliferation.

### MCP
The market signal is real: standardized tool/context interfaces appear in enterprise Agent, platform and financial roles. However, the underlying hiring value is safe reusable tool integration. The project should not exist merely to demonstrate MCP.

### Kubernetes
Useful in platform/infra roles and appears as a preference in some backend postings. It does not justify spending a large fraction of a two-month application project on cluster operations.

### RLHF/SFT/Post-training
Appears mainly as a bonus or in algorithm-mixed roles. Pure training roles were excluded by design. It is therefore not a core investment for this application-engineering portfolio unless later candidate evidence specifically requires it.

## 6. What this means for project selection

The candidate portfolio in US2 should favor projects that can visibly demonstrate all of the following within one coherent enterprise scenario:

1. A business task that cannot be solved by deterministic CRUD alone.
2. Agent judgment over next action / missing information / tool choice.
3. At least several real tools backed by deterministic business state.
4. A state-changing or otherwise externally verifiable result.
5. Failure handling, permission/approval, and idempotency for risky writes.
6. A versioned offline evaluation set and reconstructable run trace.
7. A thin vertical slice by Week 2 and a credible six-week core.
8. Technology choices that are justified by business/evidence rather than keyword collection.

This profile favors enterprise execution Agents (operations, procurement/supply-chain, data/BI with actions, R&D/DevOps workflows, transaction/service operations) over generic chat assistants or PDF-only QA.

## 7. Evidence limitations

- The snapshot is intentionally early-career biased and therefore should not be read as a complete census of all 2026 AI hiring.
- Four core records are current early-career/university recruiting pages whose titles do not explicitly say `2027`; their cohort uncertainty is preserved in `job-postings.csv` and they do not independently support 2027-specific claims.
- University employment-center reposts are authoritative enough for the defined C tier but are not equivalent to enterprise first-party pages; company-level claims should prefer A-tier evidence where available.
- Counts are coded from visible responsibilities/requirements, not raw keyword search. Framework aliases and related concepts were normalized by capability.

## 8. Contract 1 / SC-001 exit gate

| Check | Result |
|---|---|
| >=30 deduplicated relevant core postings | PASS — 30 |
| >=60% internship/campus/0–2-year sample | PASS — all 30 are early-career/university recruiting records; uncertainty is flagged where cohort title is absent |
| >=8 independent employers | PASS — 20 |
| <=5 core records per employer | PASS — maximum 5 |
| A/C evidence only in core denominator | PASS |
| Exclusion and dedupe policy documented | PASS |
| >=20% source audit | PASS — 6/30 |
| Capability conclusions preserve must/preferred/responsibility context | PASS |
| Core capability conclusions traceable to job IDs | PASS — `capability-signals.csv` |
| Senior/algorithm/aggregator contamination excluded | PASS |

**Gate 1 verdict: PASS.**

US2 may now generate 4–6 candidates, but it must use this capability map rather than the earlier preliminary market signals or discovery-only aggregator leads.
