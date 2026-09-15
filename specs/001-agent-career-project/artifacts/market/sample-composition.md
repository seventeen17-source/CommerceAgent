# Core Sample Composition

## Result

Final strict core table: `job-postings.csv`

- Deduplicated core postings: **30**
- Independent employers: **20**
- Maximum postings from one employer: **5** (南方基金)
- Internship/campus/explicit early-career postings: **30/30 (100%)**; four records are current early-career/university recruiting pages without `2027` in the job title and are explicitly marked with uncertainty notes rather than silently treated as 2027 campus roles
- Source tier A: **4**
- Source tier C (university employment-center / university-reviewed full JD): **26**
- Source tier D in core denominator: **0**
- Senior/social reference postings in core denominator: **0**

## Employer distribution

| Employer | Core records |
|---|---:|
| 百度 | 4 |
| 南方基金 | 5 |
| 神州数码融信 | 2 |
| 树根互联 | 2 |
| Coremail/论客科技 | 2 |
| 拼多多 | 1 |
| 思必驰 | 1 |
| 杉数科技 | 1 |
| 卓望数码 | 1 |
| 苏仁智能 | 1 |
| 山东省城市商业银行合作联盟 | 1 |
| 开创工软 | 1 |
| 世纪阳光纸业 | 1 |
| 金证科技 | 1 |
| 北方华创微电子 | 1 |
| 招商银行上海分行 | 1 |
| 启云方科技 | 1 |
| 国汽智联 | 1 |
| 宝盈基金 | 1 |
| 硕方信息 | 1 |

## Role-family mix

The sample intentionally mixes:
- Agent application / AI full-stack;
- LLM application / AI backend;
- Agent framework/runtime;
- Agent evaluation/quality;
- enterprise AI integration/FDE;
- adjacent AI platform/infra only when the role materially builds or operates Agent capability.

Pure pretraining, RLHF-first, CUDA/kernel-only, product, sales/solution, and senior-only roles are excluded or retained only as trend references.

## Gate checks

| Requirement | Result |
|---|---|
| >=30 deduplicated core postings | PASS (30) |
| >=8 independent employers | PASS (20) |
| <=5 core records per employer | PASS (max 5) |
| >=60% internship/campus/0–2 year | PASS (100% early-career/university recruiting; uncertainty explicitly flagged where cohort label is absent) |
| No D-tier aggregator in core denominator | PASS |
| Senior/trend roles excluded from denominator | PASS |

The sample-composition gate is therefore **PASS**, subject to the separate 20% source audit and capability-coding checks.
