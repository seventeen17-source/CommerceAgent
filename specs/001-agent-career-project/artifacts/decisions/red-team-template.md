# Three-Role Red-Team Template

Use independently for interviewer, hiring-manager, and developer review before consolidation.

| Field | Required |
|---|---|
| issue_id | Stable ID |
| role | interviewer / hiring_manager / developer |
| challenge | Specific attack, not generic pros/cons |
| severity | P0 / P1 / P2 |
| evidence_refs | Jobs, capability signals, candidate artifacts, experiments |
| failure_scenario | Concrete way the project fails in interview/business/engineering |
| alternative_candidate | Better candidate if relevant |
| proposed_cut_or_change | Feature to delete, downgrade, validate, or redesign |
| validation_method | Smallest evidence-producing action |
| disposition | accept risk / validate / downgrade / delete / switch |
| owner_or_phase | Where the action is resolved |
| old_score | Relevant pre-review score if applicable |
| new_score | Revised score after treatment if applicable |
| residual_risk | What remains after treatment |

## Severity
- **P0**: fatal to business credibility, Agent necessity, evaluation feasibility, or 6–8 week delivery; unresolved P0 rejects the candidate.
- **P1**: material weakness requiring a concrete validation, scope cut, or scheduled mitigation before final freeze.
- **P2**: useful improvement that must not displace core scope.

## Interviewer attack prompts
- Is this a tutorial clone or technology-name pile?
- Why is an Agent necessary rather than deterministic code?
- Can every claimed metric be reproduced?
- Which mechanisms must the candidate personally reimplement/explain under follow-up?
- Is there a real business-state change and failure path?

## Hiring-manager attack prompts
- Can the business value be understood in 30–60 seconds?
- Does it resemble real responsibilities in the target role family?
- Does it signal fast onboarding into a team problem rather than hobby experimentation?
- Is a more common enterprise problem better supported by job evidence?

## Developer attack prompts
- Where do data and interfaces come from?
- What happens on timeout, wrong tool, partial failure, duplicate calls, injection, and unauthorized write?
- How are cost, latency, observability, debugging, idempotency, and approval handled?
- Can one person actually deliver the Must scope in six core weeks?

## Consolidation rule
Every issue must end in exactly one primary disposition: `accept risk`, `validate`, `downgrade`, `delete`, or `switch`. Preserve the audit chain `old score → risk → action → new score` where scoring changes.
