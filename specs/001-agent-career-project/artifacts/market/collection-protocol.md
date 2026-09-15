# Market Collection Protocol

## Scope

This protocol operationalizes `spec.md`, `plan.md`, `research.md`, `data-model.md`, and `contracts/artifact-contracts.md` for US1. It does not change those source files.

## Target population

Core sample:
- Mainland China 2026 postings for 2027 campus recruitment, internship, or clearly 0–2 year early-career roles.
- Role families: Agent Application Engineer, LLM Application Engineer, AI Backend, AI Full Stack, intelligent-agent engineering, and closely related application-engineering roles.

Reference-only sample:
- Production/senior roles that reveal mature engineering requirements but do not represent early-career screening.
- Maximum 20% of the extended reference set; excluded from the early-career denominator.

Explicit exclusions:
- Pure pretraining, RLHF/post-training, CUDA/inference-kernel, research-paper-first algorithm roles, sales solution roles, product roles, and roles with no meaningful application-engineering responsibilities.

## Source-tier mapping

`research.md` uses A–D while `data-model.md` compresses the scheme. For execution, use the following mapping and preserve both labels where useful:

| Operational tier | Meaning | Core eligibility | Data-model compatibility |
|---|---|---|---|
| A | Enterprise official job detail with full JD | Yes, preferred | A |
| B | Enterprise official campus/team recruitment page; full JD if available | Yes if sufficiently detailed; otherwise direction-only | A/B note |
| C | University employment-center or similarly authoritative full repost traceable to the employer | Yes when the JD is complete and traceable | B |
| D | Aggregator/community repost/search snippet | Discovery only, not core denominator | C |

Rules:
- Core capability statistics prioritize A, then verifiable C; B without a full JD may support direction but not detailed requirement counts.
- D can discover leads but cannot independently support a core capability claim.
- If the direct page is inaccessible, record the failure and either use a traceable authoritative repost with a lower tier or exclude the record from the core denominator.

## Required fields

Every core record must contain: `job_id`, `title_raw`, `role_family`, `company`, `company_type`, `location`, `career_level`, `published_or_observed_at`, `source_url`, `source_tier`, `responsibilities`, `must_have`, `preferred`, `exclusion_reason`, `dedupe_key`, `evidence_notes`.

## Deduplication

Preferred key: `company + official_job_id`.

Fallback key: `normalized company + department/business line + normalized title + recruitment batch + responsibilities fingerprint`.

Rules:
- Same JD across cities: keep one master record; preserve city aliases in notes.
- Same JD across repost sites: keep the highest-quality source as master; preserve aliases in notes.
- Same title with materially different responsibilities: keep separate.
- High textual similarity triggers manual review; it never automatically deletes a record.

## Sampling constraints

- At least 30 deduplicated core postings.
- At least 8 independent employers.
- No more than 5 core records from one employer.
- At least 60% of the core sample must be internship/campus/0–2-year roles.
- Randomly audit at least 20% of core records.

## Coding rules

For each posting, distinguish:
- Mandatory / hard requirement.
- Preferred / bonus.
- Job responsibility / actual work.
- Business context / why the capability is used.
- Job family.
- Company type.
- Evidence strength.

Do not equate keyword presence with hiring importance. Framework names and underlying capabilities are coded separately.

## Capability confidence

- High: supported by at least 4 independent employers and at least 6 core records.
- Medium: supported by 2–3 employers or 3–5 core records.
- Low: single employer/team, reference-only evidence, or largely inferential support.

## Page-failure policy

Record access date and visible fields. Broken, anti-bot, snippet-only, or login-only pages cannot serve as sole support for a core claim. Use an authoritative alternative if available; otherwise move the record to exclusions or reference-only.
