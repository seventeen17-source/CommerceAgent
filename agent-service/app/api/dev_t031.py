"""Dev/test-only live harness for the T031 protected write + verification chain.

This is not the production graph. T032 owns LangGraph wiring. The harness exists so the Flow
Playground can prove the real durability boundary: the idempotency intent is checkpointed before
the money-moving Tool call, then the result is read back from Java authority before completion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent.execute_write import (
    CREATE_REFUND_ACTION,
    RefundWriteExecutionResult,
    execute_refund_write,
    refund_write_intent,
    write_may_already_have_committed,
)
from app.agent.state import (
    EligibilitySnapshot,
    VerificationOutcome,
    VerificationStatus,
    WriteIntent,
    WriteOutcome,
)
from app.agent.verify_business_state import verify_refund_business_state
from app.clients.commerce_client import CommerceClient
from app.security.dependencies import (
    AppSettings,
    AuthenticatedCall,
    authenticate,
    get_run_store,
)
from app.tools import CommerceTools
from app.trace.errors import (
    RunForbiddenError,
    RunNotFoundError,
    RunStoreError,
    RunVersionConflictError,
    TerminalRunError,
)

if TYPE_CHECKING:
    from app.agent.state import AgentState
    from app.trace.checkpoint import RunRecord
    from app.trace.store import RunStore

__all__ = ["router"]

router = APIRouter(
    prefix="/agent/dev/t031",
    tags=["dev-t031"],
    dependencies=[Depends(authenticate)],
)

AuthenticatedDep = Annotated[AuthenticatedCall, Depends(authenticate)]
StoreDep = Annotated["RunStore", Depends(get_run_store)]


class T031LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    run_id: str = Field(alias="runId", min_length=1, max_length=64)
    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    reason_code: str = Field(alias="reasonCode", min_length=1, max_length=100)


class T031LiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    completed: bool
    stop_reason: str | None = Field(default=None, alias="stopReason")
    run_id: str = Field(alias="runId")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
    write: WriteOutcome
    verification: VerificationOutcome
    tool_history: list[dict[str, object]] = Field(default_factory=list, alias="toolHistory")


def _client(request: Request) -> CommerceClient:
    client = getattr(request.app.state, "commerce_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COMMERCE_CLIENT_UNAVAILABLE",
        )
    return cast(CommerceClient, client)


def _parse_run_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND") from exc


def _owned_run(store: RunStore, raw_run_id: str, call: AuthenticatedCall) -> RunRecord:
    run_id = _parse_run_id(raw_run_id)
    try:
        return store.get_run_for_owner(run_id, owner_id=call.principal.user_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RUN_NOT_FOUND") from exc
    except RunForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RUN_FORBIDDEN") from exc


def _checkpoint(
    store: RunStore,
    record: RunRecord,
    state: AgentState,
    *,
    current_node: str,
    next_action: str | None,
    reason_code: str | None = None,
) -> RunRecord:
    try:
        return store.checkpoint_state(
            record.run_id,
            expected_version=record.version,
            state=state,
            current_node=current_node,
            next_action=next_action,
            reason_code=reason_code,
        )
    except RunVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RUN_STATE_CONFLICT"
        ) from exc
    except TerminalRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RUN_STATE_CONFLICT"
        ) from exc
    except RunStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RUN_STATE_CONFLICT"
        ) from exc


@router.post("/run", response_model=T031LiveResponse, response_model_by_alias=True)
async def run_t031_live(
    body: T031LiveRequest,
    request: Request,
    call: AuthenticatedDep,
    store: StoreDep,
    settings: AppSettings,
) -> T031LiveResponse:
    """Execute one real T031 refund chain with durable intent and authoritative verification."""
    if settings.environment not in {"dev", "test"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

    record = _owned_run(store, body.run_id, call)
    state = record.to_state()
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RUN_CHECKPOINT_COMPACTED"
        )
    if state.resolved_order_id is not None and state.resolved_order_id != body.order_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RESOLVED_ORDER_CONFLICT"
        )

    tools = CommerceTools(client=_client(request), auth=call.auth)
    eligibility_result = await tools.check_after_sales_eligibility(
        body.order_id, body.reason_code
    )
    if not eligibility_result.success or eligibility_result.data is None:
        return T031LiveResponse(
            completed=False,
            stopReason=eligibility_result.error_code or "ELIGIBILITY_FAILED",
            runId=body.run_id,
            write=state.write,
            verification=state.verification,
        )

    authoritative = eligibility_result.data
    eligibility = EligibilitySnapshot(
        eligible=authoritative.eligible,
        allowed_action=authoritative.allowed_action,
        max_refund_amount=authoritative.max_refund_amount,
        approval_required=authoritative.approval_required,
        rule_code=authoritative.rule_code,
        rule_version=authoritative.rule_version,
        reason_codes=authoritative.reason_codes,
    )
    if (
        not eligibility.eligible
        or eligibility.allowed_action != "REFUND_ONLY"
        or eligibility.approval_required
    ):
        return T031LiveResponse(
            completed=False,
            stopReason="WRITE_NOT_AUTHORIZED_BY_ELIGIBILITY",
            runId=body.run_id,
            write=state.write,
            verification=state.verification,
        )

    working_state = state.model_copy(
        update={
            "resolved_order_id": body.order_id,
            "eligibility": eligibility,
        }
    )
    working_record = record
    intent = refund_write_intent(
        working_state,
        order_id=body.order_id,
        reason_code=body.reason_code,
        requested_amount=None,
    )

    async def persist_intent(value: WriteIntent, pending: WriteOutcome) -> None:
        nonlocal working_record, working_state
        working_state = working_state.model_copy(
            update={"write_intent": value, "write": pending}
        )
        working_record = _checkpoint(
            store,
            working_record,
            working_state,
            current_node="execute_write",
            next_action="verify_business_state",
            reason_code="WRITE_INTENT_DURABLE",
        )

    execution: RefundWriteExecutionResult = await execute_refund_write(
        tools=tools,
        intent=intent,
        persist_intent=persist_intent,
        max_attempts=max(1, min(state.max_retries + 1, 5)),
        may_already_have_committed=write_may_already_have_committed(state),
        start_step_index=state.step_count + 1,
    )

    working_state = working_state.model_copy(
        update={
            "write": execution.outcome.to_state_outcome(),
            "tool_history": [*working_state.tool_history, *execution.history],
        }
    )
    working_record = _checkpoint(
        store,
        working_record,
        working_state,
        current_node="execute_write",
        next_action="verify_business_state",
        reason_code=execution.outcome.error_code,
    )

    if not execution.outcome.succeeded:
        return T031LiveResponse(
            completed=False,
            stopReason=execution.outcome.error_code or "WRITE_FAILED",
            runId=body.run_id,
            idempotencyKey=execution.outcome.idempotency_key,
            write=working_state.write,
            verification=working_state.verification,
            toolHistory=[
                entry.model_dump(mode="json") for entry in execution.history
            ],
        )

    verification = await verify_refund_business_state(
        tools=tools,
        order_id=body.order_id,
        idempotency_key=execution.outcome.idempotency_key,
        expected_refund_request_id=execution.outcome.resource_id,
    )
    working_state = working_state.model_copy(update={"verification": verification})
    _checkpoint(
        store,
        working_record,
        working_state,
        current_node="verify_business_state",
        next_action="finalize",
        reason_code=(
            None
            if verification.status is VerificationStatus.VERIFIED_SUCCESS
            else "VERIFY_FAILED"
        ),
    )

    return T031LiveResponse(
        completed=verification.status is VerificationStatus.VERIFIED_SUCCESS,
        stopReason=(
            None
            if verification.status is VerificationStatus.VERIFIED_SUCCESS
            else verification.status.value
        ),
        runId=body.run_id,
        idempotencyKey=execution.outcome.idempotency_key,
        write=working_state.write,
        verification=verification,
        toolHistory=[entry.model_dump(mode="json") for entry in execution.history],
    )
