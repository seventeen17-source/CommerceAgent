"""Dev/test-only live harness for observing the T030 evidence-routing chain.

This is intentionally not the production graph. T032 owns LangGraph wiring. The endpoint exists
only so the Flow Playground can execute the already-implemented T030 nodes against a real model
and the real Java authority without granting the model write capability.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.eligibility_execution import check_eligibility
from app.agent.evidence_execution import execute_read_evidence
from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceGuardDecision,
    EvidenceRoutingContext,
    NextEvidenceProposal,
    build_evidence_routing_context,
    decide_next_evidence,
    guard_evidence_proposal,
)
from app.agent.openai_evidence_routing import OpenAICompatibleEvidenceDecisionModel
from app.agent.openai_request_understanding import OpenAICompatibleRequestUnderstandingModel
from app.agent.order_resolution import OrderResolution, OrderResolutionStatus, resolve_single_order
from app.agent.request_understanding import UnderstoodRequest, understand_request
from app.agent.state import EligibilitySnapshot, EvidenceItem, ToolHistoryEntry
from app.clients.commerce_client import CommerceClient
from app.llm.openai_compatible import ModelClientError, OpenAICompatibleJsonClient
from app.security.dependencies import AppSettings, AuthenticatedCall, authenticate
from app.tools import CommerceTools, ToolRegistry

__all__ = ["router"]

router = APIRouter(
    prefix="/agent/dev/t030",
    tags=["dev-t030"],
    dependencies=[Depends(authenticate)],
)

AuthenticatedDep = Annotated[AuthenticatedCall, Depends(authenticate)]


class T030LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_request: str = Field(alias="userRequest", min_length=1, max_length=4000)


class T030EvidenceRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_index: int = Field(ge=1, le=3)
    context: EvidenceRoutingContext
    proposal: NextEvidenceProposal
    guard: EvidenceGuardDecision


class T030LiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: bool
    stop_reason: str | None = Field(default=None, alias="stopReason")
    understood: UnderstoodRequest
    order_resolution: OrderResolution = Field(alias="orderResolution")
    rounds: list[T030EvidenceRound] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    eligibility: EligibilitySnapshot | None = None
    tool_history: list[ToolHistoryEntry] = Field(default_factory=list, alias="toolHistory")


def _client(request: Request) -> CommerceClient:
    client = getattr(request.app.state, "commerce_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COMMERCE_CLIENT_UNAVAILABLE",
        )
    return cast(CommerceClient, client)


def _stop_reason_for_resolution(resolution: OrderResolution) -> str:
    if resolution.status is OrderResolutionStatus.AMBIGUOUS:
        return "ORDER_AMBIGUOUS"
    return resolution.error_code or "ORDER_UNRESOLVED"


@router.post("/run", response_model=T030LiveResponse, response_model_by_alias=True)
async def run_t030_live(
    body: T030LiveRequest,
    request: Request,
    call: AuthenticatedDep,
    settings: AppSettings,
) -> T030LiveResponse:
    """Run the T030 read-only evidence chain for the local Flow Playground."""
    if settings.environment not in {"dev", "test"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    if not settings.is_model_api_key_configured or settings.model_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MODEL_API_KEY_NOT_CONFIGURED",
        )

    tools = CommerceTools(client=_client(request), auth=call.auth)
    registry = ToolRegistry(tools=tools)

    try:
        async with OpenAICompatibleJsonClient(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model_name=settings.model_name,
            temperature=settings.model_temperature,
            timeout_seconds=settings.model_timeout_seconds,
        ) as model_client:
            understood = await understand_request(
                body.user_request,
                model=OpenAICompatibleRequestUnderstandingModel(model_client),
            )
            resolution = await resolve_single_order(understood, tools=tools)
            if resolution.status is not OrderResolutionStatus.RESOLVED:
                return T030LiveResponse(
                    completed=False,
                    stopReason=_stop_reason_for_resolution(resolution),
                    understood=understood,
                    orderResolution=resolution,
                )

            resolved_order_id = resolution.resolved_order_id
            resolved_order = resolution.order
            if resolved_order_id is None or resolved_order is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="RESOLVED_ORDER_INVARIANT_BROKEN",
                )
            evidence: list[EvidenceItem] = []
            history: list[ToolHistoryEntry] = []
            rounds: list[T030EvidenceRound] = []
            evidence_model = OpenAICompatibleEvidenceDecisionModel(model_client)

            for round_index in range(1, 4):
                context = build_evidence_routing_context(
                    understood,
                    order=resolved_order,
                    evidence=evidence,
                )
                proposal = await decide_next_evidence(context, model=evidence_model)
                guard = guard_evidence_proposal(
                    proposal,
                    resolved_order_id=resolved_order_id,
                    observed_evidence_types=set(context.observed_evidence_types),
                    registry=registry,
                )
                rounds.append(
                    T030EvidenceRound(
                        round_index=round_index,
                        context=context,
                        proposal=proposal,
                        guard=guard,
                    )
                )

                if not guard.allowed:
                    return T030LiveResponse(
                        completed=False,
                        stopReason=guard.reason_code,
                        understood=understood,
                        orderResolution=resolution,
                        rounds=rounds,
                        evidence=evidence,
                        toolHistory=history,
                    )

                if proposal.action is EvidenceAction.READY_FOR_ELIGIBILITY:
                    eligibility_result = await check_eligibility(
                        guard,
                        resolved_order_id=resolved_order_id,
                        step_index=len(history) + 1,
                        tools=tools,
                    )
                    history.append(eligibility_result.history)
                    return T030LiveResponse(
                        completed=eligibility_result.eligibility is not None,
                        stopReason=(
                            None
                            if eligibility_result.eligibility is not None
                            else eligibility_result.history.error_code or "ELIGIBILITY_FAILED"
                        ),
                        understood=understood,
                        orderResolution=resolution,
                        rounds=rounds,
                        evidence=evidence,
                        eligibility=eligibility_result.eligibility,
                        toolHistory=history,
                    )

                execution = await execute_read_evidence(
                    guard,
                    resolved_order_id=resolved_order_id,
                    step_index=len(history) + 1,
                    tools=tools,
                )
                history.append(execution.history)
                if execution.evidence is None:
                    return T030LiveResponse(
                        completed=False,
                        stopReason=execution.history.error_code or "EVIDENCE_READ_FAILED",
                        understood=understood,
                        orderResolution=resolution,
                        rounds=rounds,
                        evidence=evidence,
                        toolHistory=history,
                    )
                evidence.append(execution.evidence)

            return T030LiveResponse(
                completed=False,
                stopReason="EVIDENCE_ROUND_BUDGET_EXHAUSTED",
                understood=understood,
                orderResolution=resolution,
                rounds=rounds,
                evidence=evidence,
                toolHistory=history,
            )
    except (ModelClientError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="MODEL_RESPONSE_INVALID",
        ) from exc
