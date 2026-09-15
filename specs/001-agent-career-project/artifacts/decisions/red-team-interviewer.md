# Red Team — Interviewer Elimination Memo

Target: **CommerceAgent — E-commerce After-sales Execution & Exception Handling Agent**.

| issue | severity | attack | required treatment |
|---|---|---|---|
| Is this just `intent → refund API`? | P0 | If intermediate evidence never changes the next tool/action, there is no meaningful Agent problem | Week 2 must show logistics anomaly → refund, delivered → return, ambiguous order → clarification, high-risk → approval |
| Is this only a customer-service chatbot? | P0 | Fluent answers without business-state changes are weak | Demo must create/verify RefundRequest, ReturnRequest, SupportTicket or deliberately refuse/escalate |
| Why not a rules engine? | P1 | Many after-sales rules are deterministic | Make the boundary explicit: Agent chooses evidence/path; backend owns eligibility, money, permission and legal transition |
| Why Java + Python? | P1 | Could be resume-driven architecture | Keep split only if Java has substantial domain/transaction/idempotency logic and Python owns real Agent orchestration/eval |
| Is RAG authorizing refunds? | P0 | Model-interpreted policy cannot safely authorize money | RAG is evidence/explanation only; deterministic eligibility is authoritative |
| Are metrics cherry-picked? | P1 | Agent demos often show only wins | Frozen eval test split, Baseline/V1/Optimized comparability, run/dataset-linked claims |
| Are MCP/Multi-Agent decorative? | P2 | Buzzwords can hide weak core | MCP only after core; Multi-Agent rejected unless measured need appears |

## Verdict

**PASS conditionally.** CommerceAgent is interview-worthy only if implementation proves dynamic evidence-dependent branching, safe deterministic authority, real business writes/verification, and reproducible evaluation. Any failure of the two P0 Agent-value checks requires redesign, not more framework layers.