"""Unit tests for T033: what a run is allowed to say about itself.

The rule under test is the task's whole point - success is signed by ``VERIFIED_SUCCESS``, never
by a write response and never by a model. Each case is a terminal status plus what authority
confirmed, and the assertions are on the words a client will actually render.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.agent.state import (
    AgentState,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
    VerificationStatus,
)
from app.api.runs import _final_message, _verified_refund_request_id, _view
from app.trace.checkpoint import RunRecord


def make_state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
        "verification": {"status": VerificationStatus.NOT_RUN},
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def make_record(payload: AgentState, **overrides: Any) -> RunRecord:
    values: dict[str, Any] = {
        "run_id": payload.run_id,
        "user_id": payload.principal.user_id,
        "status": RunStatus.COMPLETED,
        "version": 3,
        "model_name": "stub-model",
        "prompt_version": "t033-v1",
        "started_at": datetime.now(UTC),
        "state": payload,
    }
    values.update(overrides)
    return RunRecord(**values)


def verified(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "status": VerificationStatus.VERIFIED_SUCCESS,
        "resource_id": "refund-001",
    }
    values.update(overrides)
    return make_state(verification=values)


def test_a_refund_id_is_published_only_when_authority_confirmed_it() -> None:
    """A write response naming an id is not enough - that is what verify-after-write is for."""
    assert _verified_refund_request_id(verified()) == "refund-001"
    for status in (
        VerificationStatus.NOT_RUN,
        VerificationStatus.PENDING,
        VerificationStatus.UNKNOWN,
        VerificationStatus.VERIFIED_FAILURE,
    ):
        assert _verified_refund_request_id(make_state(verification={"status": status})) is None


def test_a_compacted_run_publishes_no_verified_id() -> None:
    """A retired payload cannot answer the question, so null is the honest answer to it."""
    assert _verified_refund_request_id(None) is None


def test_a_verified_success_says_so_with_the_id() -> None:
    message = _final_message(RunStatus.COMPLETED, verified())

    assert message is not None
    assert "refund-001" in message
    assert "权威校验" in message


def test_a_verified_failure_does_not_read_as_a_failure_to_try() -> None:
    """Authority said there is no refund: that is a finished answer, not an error."""
    state = make_state(verification={"status": VerificationStatus.VERIFIED_FAILURE})

    message = _final_message(RunStatus.COMPLETED, state)

    assert message is not None
    assert "没有这笔退款" in message


@pytest.mark.parametrize("status", [VerificationStatus.UNKNOWN, VerificationStatus.PENDING])
def test_an_unestablished_outcome_never_reads_as_a_completion(
    status: VerificationStatus,
) -> None:
    """PENDING means a write may be in flight, so it belongs with UNKNOWN rather than with "nothing
    happened" - the two are different facts and the message must not collapse them."""
    state = make_state(verification={"status": status})

    message = _final_message(RunStatus.COMPLETED, state)

    assert message is not None
    assert "无法确认" in message


def test_a_run_that_never_wrote_says_that_instead_of_claiming_success() -> None:
    state = make_state(verification={"status": VerificationStatus.NOT_RUN})

    message = _final_message(RunStatus.COMPLETED, state)

    assert message is not None
    assert "没有产生退款写入" in message


def test_a_compacted_completion_admits_the_detail_is_gone() -> None:
    message = _final_message(RunStatus.COMPLETED, None)

    assert message is not None
    assert "回收" in message


def test_each_non_completion_status_has_its_own_ending() -> None:
    assert _final_message(RunStatus.RUNNING, None) is None
    assert "补充信息" in str(_final_message(RunStatus.WAITING_USER, None))
    assert "审批" in str(_final_message(RunStatus.WAITING_APPROVAL, None))
    assert "人工" in str(_final_message(RunStatus.ESCALATED, None))
    assert "安全边界" in str(_final_message(RunStatus.SAFE_STOP, None))
    assert "失败" in str(_final_message(RunStatus.FAILED, None))


def test_the_view_reports_the_payload_facts_and_the_version() -> None:
    """``version`` is published because it is what a client passes back to retry a write."""
    record = make_record(verified())

    view = _view(record)

    assert view.verified_refund_request_id == "refund-001"
    assert view.verification_status is VerificationStatus.VERIFIED_SUCCESS
    assert view.version == 3
    assert view.final_message is not None
    assert view.checkpoint_compacted_at is None


def test_a_compacted_record_publishes_no_payload_facts_and_says_why() -> None:
    compacted = make_record(make_state(), state=None, checkpoint_compacted_at=datetime.now(UTC))

    view = _view(compacted)

    assert view.verification_status is None
    assert view.verified_refund_request_id is None
    assert view.checkpoint_compacted_at is not None
