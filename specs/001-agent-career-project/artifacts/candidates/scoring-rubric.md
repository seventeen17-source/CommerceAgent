# Candidate Scoring Rubric

## Fatal gates (non-compensatory)
A candidate cannot become first recommendation unless all six are PASS:
1. A real `User → Agent → Tool → Business System → Result` vertical slice can be demonstrated within two weeks.
2. Core value does not depend on inaccessible private data, paid enterprise accounts, or unverifiable production integration.
3. At least one task genuinely requires uncertain Agent judgment and dynamic tool use.
4. A deterministic offline evaluation set can be constructed.
5. Reliability, safety, and observability can fit within eight weeks, not only a happy path.
6. Business value can be understood by an interviewer within roughly 60 seconds.

Any FAIL means reject or run a bounded 4–8 hour validation. Weighted score cannot compensate for a failed fatal gate.

## Fixed weights
- Enterprise demand match: 25%
- Agent technical depth: 20%
- Interview value: 20%
- Eight-week feasibility: 15%
- User background fit: 10%
- Differentiation: 10%

## Anchors
- 1: nearly irrelevant or infeasible.
- 3: limited value; major assumptions or restructuring required.
- 5: feasible but ordinary; medium evidence/interview signal.
- 7: clear match with a credible loop inside constraints.
- 9: strongly supported by multiple evidence classes; feasible, evaluable, and interview-rich.
- 10: exceptional case with unusually strong evidence and no material weakness.

Even scores interpolate adjacent anchors.

## Evidence grades and uncertainty
- A: multiple recent first-party/strong authoritative sources; default uncertainty about ±0.5.
- B: multiple sources but limited coverage; about ±1.
- C: adjacent-role evidence or design inference; about ±1.5.
- D: unverified assumption; about ±2.

Every dimension records center score, defensible interval, evidence grade, evidence refs, rationale, and what new evidence would change it.

## Weighted total
`total = demand*0.25 + agent_depth*0.20 + interview_value*0.20 + feasibility*0.15 + background_fit*0.10 + differentiation*0.10`

Store low/center/high weighted totals. Do not use false precision to hide weak evidence.

## Tie / overlap rule
If Top 1 and Top 2 center scores differ by <0.5, or weighted intervals materially overlap, do not announce a certain winner. Execute one 4–8 hour validation targeted at the ranking-sensitive uncertainty, then rescore.

Acceptable validation examples:
- verify critical data/API availability;
- run a thin tool loop;
- label 10–15 evaluation cases;
- re-check JD-to-capability mapping;
- estimate realistic implementation burden for the riskiest component.

## Sensitivity analysis
Vary each scoring dimension by a plausible ±1 point and record whether rank order changes. Ranking instability must be disclosed rather than averaged away.
