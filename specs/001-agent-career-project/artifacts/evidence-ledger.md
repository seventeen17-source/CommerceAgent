# Evidence Ledger

| evidence_id | claim_type | claim | source_url | observed_at | source_tier | evidence_strength | related_artifact | notes |
|---|---|---|---|---|---|---|---|---|

`claim_type` must be one of: `fact`, `inference`, `recommendation`, `assumption`, `target`.

Rules:
- External facts require a source URL and observation date.
- Inferences must point to supporting evidence IDs.
- Recommendations must state the decision context.
- Assumptions must include a revisit trigger.
- Targets must never be phrased as achieved results.
