"""T017 lifecycle and retention policy, asserted without a database.

The database tests in ``tests/integration/test_trace_store.py`` prove the *mechanisms* (row locks,
the version check, SQL round-trips). The tests here pin the *rules* the mechanisms enforce, and they
run in milliseconds -- which matters, because a rule checkable only against a live database
is a rule that will rarely be checked.

What is deliberately not here: a fake store. An in-memory double would have to re-implement the row
lock, and a concurrency test against it would only prove the double agrees with itself. The one
concurrency requirement T017 states is tested against PostgreSQL, with real threads.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.state import (
    AgentState,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
    VerificationStatus,
    WriteStatus,
)
from app.security.secrets import SensitiveStateError
from app.trace.checkpoint import (
    INTERRUPTED_STATUSES,
    TERMINAL_STATUSES,
    RiskLevel,
    RunRecord,
    ToolTraceRecord,
    ToolTraceStatus,
    Transition,
    TriggerKind,
)
from app.trace.errors import ResumeRefusalReason
from app.trace.retention import FAILED_STATUSES, RetentionPolicy
from app.trace.store import allowed_transitions, guard_error_code

_BEARER = "Bearer sk-live-9f8e7d6c5b4a3210"


def build_state(**overrides: object) -> AgentState:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def build_record(**overrides: object) -> RunRecord:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "user_id": "customer-001",
        "status": RunStatus.RUNNING,
        "version": 1,
        "state": build_state(),
        "model_name": "gpt-4o-mini",
        "prompt_version": "t017-v1",
        "started_at": datetime.now(UTC),
    }
    values.update(overrides)
    return RunRecord.model_validate(values)


# --------------------------------------------------------------------------------------------
# The status sets must not drift
# --------------------------------------------------------------------------------------------


def test_terminal_statuses_match_the_agent_state_definition() -> None:
    """Two copies of "terminal" exist for a reason; they must still agree.

    ``app.trace.checkpoint`` needs the set without constructing a state (to write a SQL query), and
    ``AgentState.is_terminal`` owns the runtime meaning. This test keeps the second copy from
    becoming a second answer.
    """
    for status in RunStatus:
        state = build_state(status=status)
        assert (status in TERMINAL_STATUSES) == state.is_terminal, status


def test_interrupted_statuses_are_exactly_the_non_terminal_paused_ones() -> None:
    assert INTERRUPTED_STATUSES == {RunStatus.WAITING_USER, RunStatus.WAITING_APPROVAL}
    assert INTERRUPTED_STATUSES.isdisjoint(TERMINAL_STATUSES)


def test_every_status_has_a_transition_row() -> None:
    """A missing key would raise ``KeyError`` at runtime, from inside a transaction."""
    for status in RunStatus:
        assert isinstance(allowed_transitions(status), frozenset)


def test_terminal_statuses_are_absorbing() -> None:
    for status in TERMINAL_STATUSES:
        assert allowed_transitions(status) == frozenset(), f"{status} must have no exits"


def test_a_waiting_run_can_resume_or_end_but_not_wait_elsewhere() -> None:
    """``WAITING_USER -> WAITING_APPROVAL`` would be a state change with no human decision in it."""
    for status in INTERRUPTED_STATUSES:
        allowed = allowed_transitions(status)
        assert RunStatus.RUNNING in allowed
        assert allowed.issuperset(TERMINAL_STATUSES)
        assert allowed.isdisjoint({s for s in INTERRUPTED_STATUSES if s != status})


def test_running_can_reach_every_non_initial_status() -> None:
    assert allowed_transitions(RunStatus.RUNNING) == frozenset(RunStatus)


# --------------------------------------------------------------------------------------------
# Transition and resume request shapes
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES, key=str))
def test_terminal_transitions_are_expressible(status: RunStatus) -> None:
    transition = Transition(expected_version=2, status=status, trigger="TERMINAL")

    assert transition.status is status
    assert transition.expected_version == 2


def test_a_transition_without_an_expected_version_cannot_be_built() -> None:
    """The type makes a blind overwrite unrepresentable rather than merely discouraged."""
    with pytest.raises(ValidationError):
        Transition(status=RunStatus.RUNNING, trigger="STEP")  # type: ignore[call-arg]


def test_a_transition_without_a_trigger_cannot_be_built() -> None:
    """A default trigger would silently mislabel a resume as a normal step."""
    with pytest.raises(ValidationError):
        Transition(expected_version=1, status=RunStatus.RUNNING)  # type: ignore[call-arg]


def test_transition_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        Transition.model_validate({"expected_version": 1, "status": "PAUSED", "trigger": "STEP"})


def test_every_trigger_kind_is_accepted() -> None:
    for trigger in ("CREATED", "STEP", "RESUME", "INTERRUPT", "TERMINAL"):
        assert (
            Transition(
                expected_version=1,
                status=RunStatus.RUNNING,
                trigger=trigger,  # type: ignore[arg-type]
            ).trigger
            == trigger
        )


# --------------------------------------------------------------------------------------------
# Record-derived facts
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "resumable"),
    [
        (RunStatus.RUNNING, False),
        (RunStatus.WAITING_USER, True),
        (RunStatus.WAITING_APPROVAL, True),
        (RunStatus.COMPLETED, False),
        (RunStatus.ESCALATED, False),
        (RunStatus.FAILED, False),
        (RunStatus.SAFE_STOP, False),
    ],
)
def test_only_an_interrupted_run_is_resumable(status: RunStatus, resumable: bool) -> None:
    assert build_record(status=status).resumable is resumable


def test_a_compacted_run_is_not_resumable() -> None:
    """An empty checkpoint is not a resumable checkpoint, even at the right version."""
    compacted = build_record(status=RunStatus.WAITING_APPROVAL, state=None)

    assert compacted.resumable is False
    assert compacted.to_state() is None
    assert compacted.durable_state() == {}


def test_the_row_columns_win_over_a_disagreeing_payload() -> None:
    """The direction matters: the row is what the CAS write just succeeded against."""
    record = build_record(
        status=RunStatus.WAITING_APPROVAL,
        intent="LOGISTICS_REFUND",
        step_count=4,
        state=build_state(status=RunStatus.RUNNING, step_count=0),
    )

    rebuilt = record.to_state()

    assert rebuilt is not None
    assert rebuilt.status is RunStatus.WAITING_APPROVAL
    assert rebuilt.intent == "LOGISTICS_REFUND"
    assert rebuilt.step_count == 4


def test_durable_state_matches_the_json_form() -> None:
    """Validation must run on the representation that is actually persisted."""
    record = build_record()

    payload = record.durable_state()

    assert payload["status"] == "RUNNING"
    # ``model_dump(mode="json")`` is what makes this a string rather than a UUID object.
    assert isinstance(payload["run_id"], str)


def test_run_record_rejects_a_credential_in_its_payload() -> None:
    tampered = build_state().model_dump(mode="json")
    tampered["user_request"] = f"my token is {_BEARER}"
    record = RunRecord.model_construct(
        run_id=uuid4(),
        user_id="customer-001",
        status=RunStatus.RUNNING,
        version=1,
        state=AgentState.model_construct(**tampered),
        model_name="gpt-4o-mini",
        prompt_version="t017-v1",
        started_at=datetime.now(UTC),
    )

    with pytest.raises(SensitiveStateError):
        record.durable_state()


def test_guard_error_code_names_the_field_but_not_the_value() -> None:
    error = SensitiveStateError(path="tool_history[0].trace_id", detail="credential-shaped")

    code = guard_error_code(error)

    assert code == "SENSITIVE_STATE_REJECTED:tool_history[0].trace_id"
    assert "Bearer" not in code


# --------------------------------------------------------------------------------------------
# Tool trace records
# --------------------------------------------------------------------------------------------


def build_trace(**overrides: object) -> ToolTraceRecord:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "step_index": 0,
        "tool_name": "get_logistics",
        "risk_level": RiskLevel.LOW,
        "status": ToolTraceStatus.SUCCESS,
        "trace_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
    }
    values.update(overrides)
    return ToolTraceRecord.model_validate(values)


def test_trace_rejects_a_bare_bearer_in_a_summary() -> None:
    with pytest.raises(ValidationError):
        build_trace(output_summary={"note": f"used {_BEARER}"})


def test_trace_rejects_a_forbidden_key_in_a_summary() -> None:
    with pytest.raises(ValidationError):
        build_trace(input_summary={"headers": {"authorization": "x"}})


def test_trace_accepts_the_values_the_tool_layer_actually_produces() -> None:
    """Tightening must not reject a legitimate structured summary."""
    trace = build_trace(
        input_summary={"order_id": "order-001"},
        output_summary={"status": "IN_TRANSIT", "stalled_hours": 120, "carrier": "SF"},
        error_code=None,
        latency_ms=42,
    )

    assert trace.durable_payload(path="tool_trace")["output_summary"]["stalled_hours"] == 120


def test_trace_id_must_be_a_correlation_id_not_free_text() -> None:
    """The same string reaches log lines, so CR/LF there would forge entries."""
    with pytest.raises(ValidationError):
        build_trace(trace_id="trace-001\nX-Injected: 1")


def test_dotted_trace_ids_are_still_accepted() -> None:
    """The guard's usability half: the trace layer writes dotted ids on every step."""
    trace = build_trace(trace_id="a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8")

    assert trace.trace_id == "a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8"


def test_every_tool_trace_status_is_representable() -> None:
    for status in ToolTraceStatus:
        assert build_trace(status=status).status is status


# --------------------------------------------------------------------------------------------
# Retention policy
# --------------------------------------------------------------------------------------------


def test_completed_runs_are_a_shorter_band_than_failed_runs() -> None:
    policy = RetentionPolicy()

    completed = policy.decision_for(RunStatus.COMPLETED)
    failed = policy.decision_for(RunStatus.FAILED)

    assert completed.hours < failed.hours, "a failed run is the one a reviewer re-opens"
    assert failed.retain_state is True
    assert failed.retain_tool_trace is True
    assert completed.retain_state is False
    assert completed.retain_tool_trace is False


@pytest.mark.parametrize("status", [RunStatus.ESCALATED, RunStatus.COMPLETED])
def test_a_successful_terminal_run_gives_up_its_detail(status: RunStatus) -> None:
    assert RetentionPolicy().decision_for(status).retain_state is False


@pytest.mark.parametrize("status", sorted(FAILED_STATUSES, key=str))
def test_a_failed_terminal_run_keeps_its_evidence(status: RunStatus) -> None:
    assert RetentionPolicy().decision_for(status).retain_tool_trace is True


@pytest.mark.parametrize(
    "status",
    [RunStatus.RUNNING, RunStatus.WAITING_USER, RunStatus.WAITING_APPROVAL],
)
def test_retention_refuses_to_policy_a_resumable_run(status: RunStatus) -> None:
    """Refusing is safer than returning a decision: a caller cannot compact what has no policy."""
    with pytest.raises(ValueError, match="not terminal"):
        RetentionPolicy().decision_for(status)


def test_retention_windows_cannot_be_degenerate() -> None:
    with pytest.raises(ValueError, match="at least one hour"):
        RetentionPolicy(completed_state_hours=0)

    with pytest.raises(ValueError, match="at least one hour"):
        RetentionPolicy(failed_state_hours=-1)


def test_retention_policy_is_injectable() -> None:
    """Eval needs to tighten the window without editing a constant."""
    policy = RetentionPolicy(completed_state_hours=1, failed_state_hours=2, failed_trace_hours=2)

    assert policy.decision_for(RunStatus.COMPLETED).hours == 1


def test_the_two_cutoffs_are_independent() -> None:
    """A run started 30 days ago is past the completed window but inside the failed window."""
    policy = RetentionPolicy()
    now = datetime.now(UTC)
    started = now - timedelta(days=30)

    assert started < now - timedelta(hours=policy.completed_state_hours)
    assert started > now - timedelta(hours=policy.failed_state_hours)


# --------------------------------------------------------------------------------------------
# Vocabulary shared with the state machine
# --------------------------------------------------------------------------------------------


def test_write_and_verification_statuses_still_round_trip_through_json() -> None:
    """The store serializes the whole state, so these must survive ``mode="json"`` unchanged."""
    state = build_state(
        write={"status": WriteStatus.UNKNOWN, "action": "CREATE_REFUND_REQUEST"},
        verification={"status": VerificationStatus.PENDING},
    )

    payload = state.model_dump(mode="json")
    restored = AgentState.model_validate(payload)

    assert restored.write.status is WriteStatus.UNKNOWN
    assert restored.verification.status is VerificationStatus.PENDING


def test_trigger_kind_vocabulary_is_exhaustive() -> None:
    """``TriggerKind`` is a ``Literal``, so the set is documentation plus a runtime check."""
    assert set(TriggerKind.__args__) == {  # type: ignore[attr-defined]
        "CREATED",
        "STEP",
        "RESUME",
        "INTERRUPT",
        "TERMINAL",
    }


def test_resume_refusal_reasons_are_a_closed_set() -> None:
    """This service owns this set and must branch on every member."""
    assert {reason.value for reason in ResumeRefusalReason} == {
        "VERSION_MISMATCH",
        "ALREADY_CLAIMED",
        "STATUS_NOT_WAITING",
        "TERMINAL",
        "CHECKPOINT_COMPACTED",
    }
