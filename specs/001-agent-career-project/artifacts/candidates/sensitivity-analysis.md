# Candidate Score Sensitivity Analysis

## Base ranking

1. C1 Procurement & Supplier Execution — **8.880**
2. C5 Financial Operations/Policy Compliance — **8.860**
3. C2 DevOps/R&D Incident — **8.765**
4. C3 Data/BI Decision-to-Action — **8.655**
5. C4 Enterprise Email/Internal Workflow — **8.500**
6. C6 Merchant/E-commerce Operations — **8.290**

The Top-1/Top-2 gap is **0.020**, far below the 0.5 trigger. All top-four defensible weighted intervals overlap materially. A certain winner is therefore prohibited before bounded validation.

## Weight sensitivity

Because the fixed weights must not change, sensitivity varies scores rather than weights. A plausible ±1 change moves weighted total by:

- demand: ±0.25
- Agent depth: ±0.20
- interview value: ±0.20
- feasibility: ±0.15
- background fit: ±0.10
- differentiation: ±0.10

Therefore C1 vs C5 can flip on **any** single plausible scoring correction. C2 can also overtake both if feasibility is validated higher than the current center or if C1/C5 lose one evidence-backed point in a high-weight dimension.

## Ranking-sensitive dimensions

### C1 Procurement
- **Demand evidence** is the main downside uncertainty: strict-core evidence supports supply-chain/operations and enterprise execution, but few roles are explicitly procurement-titled.
- **Feasibility/background fit** are the main upside: bounded domain, deterministic business state, and strong backend fit make a thin vertical slice credible.

### C5 Financial Operations
- **Demand evidence** is strongest: multiple finance employers explicitly recruit Agent/LLM application, eval and FDE roles.
- **Feasibility/domain burden** is the main downside: careless scope can introduce regulatory/safety claims and domain explanation cost.

### C2 DevOps/R&D Incident
- **Demand/interview depth** are strong and directly supported by AI-Coding, R&D efficiency, platform and observability roles.
- **Feasibility** is ranking-sensitive: real infrastructure would be too expensive, while a small deterministic service simulator may preserve the signal.

### C3 Data/BI
- Stable feasibility and broad enterprise value.
- Ranking depends on proving the project is more than NL2SQL and has a meaningful state-changing action.

## Required action

The scoring rubric's close-ranking trigger is active. Execute a bounded validation comparing C1 and C5 on:
1. ability to specify 10–15 deterministic eval cases;
2. minimal Tool/business-state surface;
3. Week-2 vertical-slice complexity;
4. 60-second business explanation;
5. unresolved domain/safety assumptions;
6. direct hiring-evidence mapping.

C2 is retained as the strongest fallback if the validation shows both C1 and C5 have unacceptable hidden scope.
