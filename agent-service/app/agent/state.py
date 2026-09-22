"""Explicit Agent state for CommerceAgent orchestration.

This module defines the data that graph nodes may read and update while one Agent run is
executing. It deliberately contains no HTTP client, JWT, database, or LangGraph runtime code.

Security boundary:
- Keep only derived principal context (user_id / role), never a raw JWT or credential.
- Store verified business evidence and backend decisions as structured snapshots.
- Persisting/restoring this state is a T017 concern.
- The credential rule itself lives in :mod:`app.security.secrets` and is applied to the *whole*
  JSON form of this model by :meth:`AgentState.reject_sensitive_content`. It is applied again at
  the persistence boundary, because a state restored from a raw checkpoint dict never passes
  through this class at all. Two call sites, one rule -- see that module for why a per-field
  allowlist was rejected.

Persistence boundary (T017) -- this object is deliberately NOT the `agent.agent_runs` row:
- Row-only run metadata belongs to the table, not here: `current_node`, `next_action`,
  `final_action`, run-level `error_code`, `model_name`, `model_temperature`, `prompt_version`,
  `input_tokens`, `output_tokens`, `started_at`, `completed_at`. See
  `commerce-backend/src/main/resources/db/migration/V001__core_schema.sql` and
  `specs/002-commerce-after-sales-agent/data-model.md` section 12.
- `status`, `intent`, `resolved_order_id`, `step_count`, `retry_count` intentionally exist in
  both places: the row column is the *queryable projection*, this object (serialized into
  `state_json`) is the authoritative copy of the *runtime* state. T017 owns writing both in one
  transaction and must not let the two drift.
- Being stored here still grants nothing: `AgentRun.status` is not business authorization.

Cross-service value policy (why some fields are `str`, not `StrEnum`):
- `StrEnum` is used only for value sets this service owns and must branch on exhaustively
  (run lifecycle, write/verification status, principal role).
- Values owned by the Java backend (`allowed_action`, approval `status`, `error_code`) stay open
  strings on purpose. Mirroring a remote enum here would turn an additive Java change into a
  Python parse failure and would add a fourth copy of a set already declared in
  `AllowedAction.java`, the V001 CHECK constraint, and `data-model.md`.
- An unknown remote value must degrade controllably (`SAFE_STOP` plus a reason code), never into
  "the response failed to parse": a strict enum cannot distinguish a benign additive rollout
  from a corrupt payload, and both would surface as an unhandled validation error.
- Never infer permission from an unknown or absent value: a write is unlocked only by an
  explicit positive confirmation from the backend.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.security.secrets import SensitiveStateError, validate_persistable

#: Control characters (CR/LF/TAB) are rejected anywhere in a machine-produced identifier. This is a
#: *shape* rule, not a security rule: the credential rule lives in ``app.security.secrets``. What it
#: buys is that a model-produced value cannot smuggle a line break into a trace, a log line, or a
#: future query parameter. It deliberately allows uppercase and non-ASCII text, so an unexpected but
#: harmless value cannot stop a run for a cosmetic reason.
_IDENTIFIER_PATTERN = r"^[^\x00-\x1f\x7f]+$"

#: A machine-produced identifier: bounded, non-empty, and free of control characters. Annotated
#: rather than repeated inline so the list and scalar forms of an order id cannot drift apart.
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)]


class PrincipalRole(StrEnum):
    """Application role copied from the authenticated principal."""

    CUSTOMER = "CUSTOMER"
    APPROVER = "APPROVER"
    SUPPORT = "SUPPORT"


class RunStatus(StrEnum):
    """Lifecycle status shared with the persisted AgentRun model."""

    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"
    SAFE_STOP = "SAFE_STOP"


class WriteStatus(StrEnum):
    """State of a business write attempt."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    """Result of authoritative write-after-read verification."""

    NOT_RUN = "NOT_RUN"
    PENDING = "PENDING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    UNKNOWN = "UNKNOWN"


class PrincipalContext(BaseModel):
    """Authenticated identity facts derived by the security layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: Identifier
    role: PrincipalRole


class EvidenceItem(BaseModel):
    """One structured, already-observed business fact used by the Agent."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def reject_sensitive_persisted_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_persistable(value, "evidence.data")
        return value


class EligibilitySnapshot(BaseModel):
    """Deterministic eligibility result returned by the Java backend."""

    model_config = ConfigDict(extra="forbid")

    eligible: bool
    # Owned by Java `AllowedAction` + the V001 CHECK constraint. Open string on purpose: see the
    # cross-service value policy in the module docstring. Unknown values must safe-stop.
    allowed_action: str = Field(min_length=1, max_length=32)
    max_refund_amount: Decimal | None = None
    approval_required: bool
    # None together with rule_version when Java could not determine an applicable rule (T020): a
    # MANUAL_REVIEW decision may legitimately cite no rule. The pairing is validated below, and the
    # absent value must never be read as "a rule approved this" -- approval is only ever the
    # explicit `eligible`/`allowed_action` pair plus, for money, an explicit `max_refund_amount`.
    rule_code: str | None = Field(default=None, max_length=100)
    rule_version: int | None = Field(default=None, ge=1)
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rule_citation(self) -> EligibilitySnapshot:
        """Keep the producer's "all or nothing" rule: a half-cited rule is a corrupt snapshot."""
        if (self.rule_code is None) != (self.rule_version is None):
            raise ValueError("rule_code and rule_version are cited together or not at all")
        return self


class ApprovalSnapshot(BaseModel):
    """Authoritative approval reference/state observed from the backend."""

    model_config = ConfigDict(extra="forbid")

    approval_request_id: str | None = Field(default=None, max_length=128)
    # Owned by the Java approval state machine. Only a positively confirmed value may unlock a
    # write; unknown/absent must never be read as approval.
    status: str | None = Field(default=None, max_length=32)


class ToolHistoryEntry(BaseModel):
    """Compact per-step Tool execution summary kept in Agent state."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    tool_name: str = Field(min_length=1, max_length=100)
    success: bool
    # Java `ErrorCode` / tool-contract code. Python branches on the few codes it understands and
    # safe-stops on the rest; it deliberately does not mirror the full error catalogue.
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False
    trace_id: str | None = Field(default=None, max_length=128)


class WriteOutcome(BaseModel):
    """Most recent state-changing action outcome."""

    model_config = ConfigDict(extra="forbid")

    status: WriteStatus = WriteStatus.NOT_ATTEMPTED
    action: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=128)
    # See `ToolHistoryEntry.error_code`: same cross-service code space, same policy.
    error_code: str | None = Field(default=None, max_length=100)


class VerificationOutcome(BaseModel):
    """Authoritative verification performed after a write attempt."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus = VerificationStatus.NOT_RUN
    resource_id: str | None = Field(default=None, max_length=128)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def reject_sensitive_persisted_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_persistable(value, "verification.details")
        return value


class AgentState(BaseModel):
    """Single explicit state object shared by all nodes of one Agent run."""

    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    principal: PrincipalContext
    # Untrusted natural-language input. It may guide intent understanding but never authorization.
    user_request: str = Field(min_length=1, max_length=4000)

    intent: str | None = Field(default=None, max_length=100, pattern=_IDENTIFIER_PATTERN)
    candidate_order_ids: list[Identifier] = Field(default_factory=list)
    resolved_order_id: Identifier | None = None

    evidence: list[EvidenceItem] = Field(default_factory=list)
    eligibility: EligibilitySnapshot | None = None
    approval: ApprovalSnapshot | None = None
    tool_history: list[ToolHistoryEntry] = Field(default_factory=list)

    # Safety budgets. The configurable values live in `app.config.settings`
    # (`agent_max_steps` / `agent_max_retries`) and are injected by run creation (T017/T018);
    # these defaults are only a last-resort safety net so a directly constructed state can
    # never be unbounded. A restored checkpoint keeps the budgets it was created with.
    step_count: int = Field(default=0, ge=0)
    max_steps: int = Field(default=12, ge=1)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)

    write: WriteOutcome = Field(default_factory=WriteOutcome)
    verification: VerificationOutcome = Field(default_factory=VerificationOutcome)
    status: RunStatus = RunStatus.RUNNING

    @model_validator(mode="after")
    def validate_budgets(self) -> AgentState:
        """Fail closed if a restored or mutated state already exceeds a safety budget."""
        if self.step_count > self.max_steps:
            raise ValueError("step_count cannot exceed max_steps")
        if self.retry_count > self.max_retries:
            raise ValueError("retry_count cannot exceed max_retries")
        return self

    @model_validator(mode="after")
    def reject_sensitive_content(self) -> AgentState:
        """Scan the *whole* JSON form of this state, not a hand-picked list of fields.

        The previous design decorated ``evidence.data`` and ``verification.details`` only. A probe
        across all 16 free-text fields showed that 26 of 32 credential injections were accepted, and
        -- the part that actually matters -- a field added tomorrow would have been accepted by
        default. Attaching the rule to the model instead of to fields inverts the default: new
        fields are covered unless someone deliberately exempts them.

        ``mode="json"`` is not cosmetic. ``UUID`` and ``Decimal`` only become strings in JSON mode,
        and the walker inspects strings; validating ``model_dump()`` would check a representation
        that is never persisted.

        This is defence in depth, not the last line: T017 calls
        :func:`app.security.secrets.validate_persistable` again on the payload it is about to write,
        because a checkpoint restored through a raw dict never passes through here at all.
        """
        try:
            validate_persistable(self.model_dump(mode="json"), "state")
        except SensitiveStateError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def is_terminal(self) -> bool:
        """Whether no automatic graph execution should continue for this run."""
        return self.status in {
            RunStatus.COMPLETED,
            RunStatus.ESCALATED,
            RunStatus.FAILED,
            RunStatus.SAFE_STOP,
        }
