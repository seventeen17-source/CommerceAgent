# Source Audit — 20% Core Sample

Audit date: 2026-09-15

Audit size: **6/30 = 20%**. Records were selected across source tiers, company types, and role families rather than all from one employer.

| job_id | Source check | Title/company | Career level | Responsibilities & requirement coding | Dedupe check | Result |
|---|---|---|---|---|---|---|
| Baidu-J99974 | Direct Baidu talent page accessible | Agent应用全栈 / 百度 | 2027 campus | Planning/Tool/Memory/RAG/eval/cost-latency claims visible | official job id unique | PASS |
| PDD-AI-Agent-2027 | Beijing Sport University employment center full repost accessible | AI Agent研发 / 拼多多 | 2027 campus | Planning/Context/Memory/Tool/RAG/high-availability/security/observability visible | duplicate mirror variants excluded | PASS |
| AISpeech-Agent-2027 | Nankai employment center full JD accessible | AI Agent研发 / 思必驰 | 2027 campus | multi-agent/planning/memory/tool orchestration/performance/productization visible | single master record | PASS |
| Coremail-AIDev-2027 | Nankai/HUST university employment page accessible | AI开发 / Coremail | 2027 campus | enterprise Agent/Tool/RAG/context/business-system/eval visible | AI测试 role kept separately because responsibilities differ materially | PASS |
| SouthernFund-AIFramework-2027 | HUST full role table accessible | AI框架 / 南方基金 | 2027 campus | state-machine orchestration/routing/context/Tool/Graph RAG visible | one of five distinct role families; employer cap not exceeded | PASS |
| NAURA-Agent-J16415 | Nankai individual job page accessible | Agent开发 / 北方华创 | 2027 campus | multi-step/workflow/routing/Tool/Skill plus Java requirement visible | official J16415 unique | PASS |

## Corrections made during audit

1. The initial discovery batches contained many Nowcoder records marked too optimistically as source tier C. Under `research.md`, aggregator/recruitment-platform pages are discovery tier D unless promoted through an authoritative source. They were removed from the final core denominator.
2. The final `job-postings.csv` was rebuilt using only A-tier enterprise official pages and C-tier university employment-center / university-reviewed full JDs.
3. Direction-only university pages without enough responsibility/requirement detail were not used for capability counts.

## Audit verdict

- Source accessibility: **6/6 PASS**
- Title/company/career-level match: **6/6 PASS**
- Responsibility/requirement coding is materially supported: **6/6 PASS**
- Dedupe review: **6/6 PASS**

**20% source-audit gate: PASS.**

Remaining caveat: four early-career records do not explicitly place `2027` in the job title; their uncertainty is preserved in `job-postings.csv` and they should not be used alone to make cohort-specific claims.
