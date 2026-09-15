# Red Team — Interviewer Elimination Memo

Target: C1 Procurement & Supplier Execution Agent. Alternatives: C2 DevOps/R&D Incident, C5 Financial Operations.

| issue_id | severity | challenge | evidence / failure scenario | proposed disposition |
|---|---|---|---|---|
| INT-01 | P0 | Why is this an Agent rather than deterministic procurement rules + forms? | Budget, approval, supplier eligibility and final writes are deterministic; if the only LLM job is parsing a sentence, the project is CRUD with decoration | **validate / narrow Agent boundary**: Agent owns incomplete-intent resolution, dynamic evidence/tool choice and multi-constraint option comparison; backend owns all deterministic policy/state. If eval cannot prove these decisions matter, switch candidate |
| INT-02 | P1 | Procurement-specific hiring demand is weaker than the project name implies | Gate-1 evidence supports enterprise execution/supply-chain integration but few strict-core roles are explicitly procurement-titled | **accept risk + compare C2**: do not claim procurement is a hiring category; sell it as an enterprise execution Agent. Lower demand score if necessary |
| INT-03 | P1 | Can the candidate be deeply questioned about failures, or is it a polished happy-path demo? | Typical student Agent demos hide retry, duplicate writes, injection, approval and trace details | **retain core**: timeout, duplicate/idempotency, injection, wrong-tool/parameter, high-risk approval and partial-failure cases remain Must |
| INT-04 | P1 | Supplier recommendation metrics can be subjective and easy to cherry-pick | Several supplier choices may be acceptable, making “accuracy” hard to defend | **redesign eval oracle**: evaluate constraint satisfaction, allowed tool sequence, forbidden actions, Pareto/score predicates and resulting business state rather than one exact natural-language answer |
| INT-05 | P1 | A Java backend plus Python Agent could look like architecture theater if the split is arbitrary | Two services increase complexity; interviewer may ask why one language cannot do both | **technology-neutral now**: later choose boundaries only if deterministic domain/transaction logic and Agent orchestration justify them; no language split solely for resume keywords |
| INT-06 | P2 | MCP/Multi-Agent can become buzzword bait | Both are visible in JDs but unnecessary for the base procurement loop | **delete from core**: MCP at most Should; Multi-Agent Reject unless a measured single-Agent limitation appears |

## Interviewer verdict

C1 survives only conditionally. INT-01 is the decisive attack. The project is interview-worthy if evaluation demonstrates that the Agent must resolve ambiguity and choose evidence/actions dynamically while deterministic code protects business truth. If the final design cannot show that separation cleanly, C2 is a stronger technical story.
