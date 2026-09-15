# Candidate Evidence Matrix

This matrix links candidates to Gate-1 evidence. It does not treat project ideas as hiring facts.

| Candidate | Strongest supporting jobs | Capability signals | Target role families | Contradictory / missing evidence |
|---|---|---|---|---|
| C1 Procurement & Supplier Execution | Suren-Agent-2027 (explicit operations/product/supply-chain Agent); SunPaper-AI-2027 (ERP/MES/OA/WMS integration); NAURA-Agent-J16415 (internal operations Agent); SouthernFund-FDE-2027; Guoqi-AI-2026 | CAP002 Tool/API; CAP003 workflow/state; CAP005 eval/obs; CAP006 business integration; CAP008 safe writes | Agent application; AI backend; enterprise integration/FDE | No strict-core JD is titled “procurement Agent”; demand score must reflect this gap rather than infer a universal procurement market |
| C2 DevOps/R&D Incident Agent | DCITS-AICoding-2027; NAURA-Agent-J16415 (研发效能); SouthernFund-Platform-2027 (DevOps/observability Agent); Guoqi-AI-2026 (R&D tools + MCP); Baidu-J100835 | CAP001 backend; CAP002 tools; CAP003 state; CAP005 eval/obs; CAP007 reliability; CAP009 MCP | AI backend; Agent platform; R&D efficiency; Agent framework | Infrastructure scope can overwhelm the Agent problem; evidence is strong for R&D/platform Agents but not specifically “incident remediation” |
| C3 Data/BI Decision-to-Action | SouthernFund-AIApp-2027; SouthernFund-AIFramework-2027; BankAlliance-LLM-2027; SunPaper-AI-2027; Shanshu-Agent-2027 | CAP001 backend; CAP002 tools; CAP003 workflow; CAP004 retrieval; CAP005 eval; CAP006 business integration | Data/AI backend; enterprise Agent; FDE | Can collapse into Text-to-SQL if the action/decision layer is weak; strict sample has fewer explicit Data Agent titles than initial discovery leads |
| C4 Email/Internal Workflow Agent | Coremail-AIDev-2027; Coremail-AITest-2027; NAURA-Agent-J16415; Baoying-AI-2026; SouthernFund-FDE-2027 | CAP002 tools; CAP003 context/state; CAP004 RAG; CAP005 eval; CAP008 security; CAP011 HITL | Enterprise Agent application; full-stack; quality/eval | Strong direct evidence is concentrated in one email vendor, so avoid claiming universal email demand; differentiation is lower |
| C5 Financial Operations/Policy Compliance | DCITS-Agent-2027; BankAlliance-LLM-2027; Kingdom-LLM-2027; SouthernFund-AIFramework/AIEval/AIApp/FDE-2027; CMB-SH-AI-2027; Baoying-AI-2026 | CAP002 tools; CAP003 workflow; CAP004 RAG; CAP005 eval; CAP006 integration; CAP008 safe writes; CAP009 MCP | Financial AI application; Agent backend; FDE; eval/quality | Very strong hiring evidence but higher domain/safety burden; must stay synthetic and operational rather than investment advice |
| C6 Merchant/E-commerce Operations | Suren-Agent-2027 (operations/supply-chain); PDD-AI-Agent-2027 (general e-commerce employer Agent); CAP006 enterprise integration evidence | CAP002 tools; CAP003 workflow; CAP005 eval; CAP006 integration; CAP007 reliability | Agent application; AI full-stack; operations | Much of the strongest e-commerce-specific discovery evidence came from D-tier aggregator leads and is excluded; strict-core support is weaker than financial/R&D directions |

## Evidence interpretation rules

- Job IDs support capability/role demand, not an assertion that the exact proposed product already exists at that employer.
- Candidate demand scores are lower when support is indirect or concentrated in one employer/domain.
- CAP009 (MCP) and CAP010 (Multi-Agent) do not automatically raise a candidate score; they contribute only when the scenario needs them.
- Background-fit scoring treats existing backend/Java strength as an asset and explicitly prices the cost of Python/Agent engineering learning.
