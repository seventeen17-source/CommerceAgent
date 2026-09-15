<!--
Sync Impact Report
- Version change: template placeholder -> 1.0.0
- Modified principles: all template placeholders replaced by project-specific governance
- Added sections: Architecture & Security Constraints; Development Workflow & Quality Gates
- Removed sections: none; placeholder-only content replaced
- Follow-up TODOs: none
-->

# CommerceAgent Constitution

## Core Principles

### I. Deterministic Business Authority
The LLM/Agent MAY interpret user intent, resolve ambiguity, decide what evidence is needed next,
select from allowlisted tools, and choose among business paths that the backend has declared legal.
The LLM/Agent MUST NOT be authoritative for order ownership, authentication, authorization,
refund/return eligibility, refund amount, legal state transitions, approval requirements,
idempotency, or transaction success. Every money- or state-changing action MUST be revalidated
against current authoritative business state by the Java backend immediately before commit.

Rationale: the project is intended to demonstrate useful Agent reasoning without delegating
financial or transactional authority to probabilistic model output or retrieved prose.

### II. Safe, Idempotent, Verifiable Writes
Every state-changing capability MUST enforce authentication, authorization, deterministic
validation, idempotency, transactional consistency where applicable, audit recording, and
post-write verification. A timeout or unknown write outcome MUST NOT trigger a blind retry.
Recovery MUST first query authoritative business state and MAY retry only with the same logical
idempotency context when the backend proves that no conflicting write exists.

Rationale: a demo that can duplicate refunds or claim success without verified state is not an
acceptable enterprise Agent implementation.

### III. Evidence-Dependent Agent Behavior
The Agent MUST maintain explicit task state and choose its next action from current evidence rather
than follow one fixed refund-like workflow. The same high-level user request under materially
different seeded business states MUST be able to produce different outcomes such as clarification,
refund, return, approval, escalation, denial, or safe stop. The Agent MUST have bounded step/retry
budgets and MUST stop when no new evidence can be obtained.

Rationale: this is the project's Agent Value Gate. If evidence cannot change the next action, the
feature should be implemented as deterministic workflow code instead of being presented as Agent
reasoning.

### IV. Untrusted Inputs, Retrieval, and Model Output
User text, retrieved policy text, model-generated arguments, and external tool results MUST be
treated as untrusted data until validated. Retrieved policy/SOP content MAY provide explanation,
context, and citations but MUST NOT alter authentication, tool allowlists, refund amount,
eligibility, approval state, or backend permissions. The Agent MUST NOT be able to supply arbitrary
internal URLs, SQL, service names, or executable code as a substitute for registered tools.

Rationale: prompt injection and poisoned retrieval must fail closed at deterministic boundaries.

### V. Reproducible Tests, Eval, and Trace
Business invariants and high-risk paths MUST have automated tests before the corresponding feature
is considered complete. Agent behavior MUST be evaluated on versioned, resettable fixtures with
explicit expected tool constraints and final business-state oracles wherever possible. Baseline and
Agent variants MUST use comparable dataset versions, permissions, reset state, and metric
definitions. Public performance, safety, latency, cost, or improvement claims MUST be backed by a
reproducible run artifact. Trace data MUST capture structured state transitions, tools, validated
parameter summaries, results/errors, retries, approval state, write result, and verification result,
but MUST NOT persist or expose hidden chain-of-thought.

Rationale: project value comes from measurable behavior and inspectable failure modes, not a small
number of curated successful demos.

### VI. Bounded Architecture and Scope
The core implementation MUST remain the smallest architecture that preserves the business/Agent
boundary: one Java modular monolith, one Python Agent service, one lightweight web client, and one
PostgreSQL datastore are sufficient unless measured evidence proves otherwise. Microservice
splitting, Kafka, Kubernetes, Redis as core state, independent vector databases, Multi-Agent
orchestration, real payment/provider integrations, or broad commerce features MUST NOT be added to
the core scope without a documented requirement and an equal-or-larger scope tradeoff.

Rationale: complexity is acceptable only when it solves a demonstrated problem and remains
explainable in a 6-8 week solo project.

## Architecture & Security Constraints

- Java owns authoritative commerce state, business invariants, authorization, deterministic
  eligibility, legal state transitions, idempotency, approval validation, audit, and transactional
  writes.
- Python owns Agent state/orchestration, LLM interactions, allowlisted tool adapters, policy
  retrieval, checkpoint/resume behavior, structured Agent trace, and offline evaluation.
- The Agent MUST NOT read or write commerce database tables directly; business access goes through
  typed backend contracts.
- Authentication context MUST come from the application/security layer and MUST NOT be inferred
  from prompt text. Tokens and credentials MUST NOT be inserted into prompts or stored in trace.
- Human approval MUST be represented by an authoritative backend record. The Agent MAY reference
  an `approvalRequestId` but MUST NOT mint or assert an approved token/state itself.
- PostgreSQL MAY host separate logical schemas for commerce, Agent runtime/eval, and policy
  retrieval. Schema ownership and migrations MUST be explicit; shared-database convenience MUST
  NOT blur service authority.
- Evaluation-only reset/fixture endpoints MUST be unavailable outside test/eval profiles.

## Development Workflow & Quality Gates

1. **Spec before implementation**: `spec.md`, `plan.md`, data model, contracts, and `tasks.md` MUST
   agree before implementation begins.
2. **Tests before risky behavior**: authorization, eligibility, state transition, idempotency,
   timeout recovery, approval, and prompt-injection boundaries MUST have automated tests as part of
   their story implementation.
3. **MVP gate**: the logistics-anomaly refund slice MUST work end to end—Agent to Java to
   PostgreSQL to verified result and trace—before optional framework/infrastructure expansion.
4. **Agent Value gate**: before calling the system a completed Agent project, the same refund-like
   request MUST be demonstrated against seeded states that lead to refund, return, clarification,
   and approval paths.
5. **Safety gate**: no cross-user write, approval bypass, duplicate logical refund/return, or
   model-authorized financial action may be accepted in the frozen adversarial test set.
6. **Evidence gate**: README/resume/demo numbers MUST be linked to actual versioned eval output;
   target values are not achievements.
7. **Scope change rule**: after the core Week-2 slice is underway, any new Must-have capability
   requires removing or deferring comparable scope.

## Governance

This constitution is the highest project-level engineering authority for CommerceAgent. Feature
specifications, implementation plans, task lists, and code reviews MUST comply with it. A design or
implementation that conflicts with a MUST rule cannot be justified by convenience, framework
defaults, or model capability.

Amendments require:
1. a documented reason and affected principles;
2. an explicit version change using semantic versioning;
3. migration/update notes for affected spec, plan, contracts, tasks, tests, and documentation;
4. a new consistency analysis before implementation continues when the amendment changes an
   existing feature boundary.

Versioning policy:
- MAJOR: removes/redefines a non-negotiable principle or changes authority/security boundaries;
- MINOR: adds a new principle or materially expands governance requirements;
- PATCH: clarification that does not change required behavior.

Every implementation PR MUST review at least: deterministic authority, safe writes, Agent Value,
input/retrieval trust boundary, reproducible evidence, and scope simplicity.

**Version**: 1.0.0 | **Ratified**: 2026-09-15 | **Last Amended**: 2026-09-15
