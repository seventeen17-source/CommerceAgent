"""T062 executable HTTP and LangGraph manual-handoff contract."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.agent.nodes import build_lifecycle_nodes
from app.agent.routing import Node, SafeStopReason
from app.agent.state import AgentState, RunStatus
from app.clients.auth import AuthContext
from app.clients.commerce_client import TRACE_ID_HEADER, CommerceClient
from app.clients.models import TicketResult
from app.tools.commerce_tools import CommerceTools
from app.tools.models import ToolEnvelope

_AUTH = AuthContext(token="header.payload.signature")


def _state() -> AgentState:
    return AgentState.model_validate(
        {
            "run_id": uuid4(),
            "principal": {"user_id": "customer-001", "role": "CUSTOMER"},
            "user_request": "My order needs manual review",
            "resolved_order_id": "order-001",
            "eligibility": {
                "eligible": False,
                "allowed_action": "MANUAL_REVIEW",
                "approval_required": False,
                "reason_codes": ["MANUAL_REVIEW_REQUIRED"],
            },
            "evidence": [
                {
                    "evidence_type": "LOGISTICS",
                    "source": "get_logistics",
                    "data": {"status": "IN_TRANSIT"},
                }
            ],
            "step_count": 4,
        }
    )


def _client(handler: object) -> CommerceClient:
    return CommerceClient(
        base_url="http://commerce.test/api/v1",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_ticket_tool_forwards_principal_and_only_contract_fields() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            201,
            json={"ticketId": "ticket-001", "status": "OPEN"},
            headers={TRACE_ID_HEADER: "java-ticket-trace"},
        )

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_support_ticket(
            run_id=str(uuid4()),
            order_id="order-001",
            category="AFTER_SALES_ESCALATION",
            reason_code="MANUAL_REVIEW_REQUIRED",
            evidence_summary="eligibility=MANUAL_REVIEW; evidenceTypes=LOGISTICS",
        )
    assert result.success is True
    assert result.data is not None and result.data.ticket_id == "ticket-001"
    assert result.trace_id == "java-ticket-trace"
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/v1/support-tickets"
    assert seen[0].headers["authorization"] == "Bearer header.payload.signature"
    assert set(json.loads(seen[0].content)) == {
        "runId",
        "orderId",
        "category",
        "reasonCode",
        "evidenceSummary",
    }


@pytest.mark.asyncio
async def test_timeout_never_blind_retries_and_does_not_forge_ticket() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        raise httpx.ReadTimeout("result unknown", request=req)

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_support_ticket(
            run_id=str(uuid4()),
            order_id=None,
            category="AFTER_SALES_ESCALATION",
            reason_code="MANUAL_REVIEW_REQUIRED",
            evidence_summary="eligibility=MANUAL_REVIEW",
        )
    assert len(calls) == 1
    assert result.success is False
    assert result.error_code == "WRITE_TIMEOUT_UNKNOWN"
    assert result.retryable is False
    assert result.data is None


@pytest.mark.asyncio
async def test_invalid_ticket_request_is_rejected_before_http() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(201, json={"ticketId": "fake", "status": "OPEN"})

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_support_ticket(
            run_id=str(uuid4()),
            order_id=None,
            category="AFTER_SALES_ESCALATION",
            reason_code="",
            evidence_summary="structured",
        )
    assert calls == []
    assert result.error_code == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_unexpected_http_200_does_not_claim_ticket_created() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ticketId": "ticket-001", "status": "OPEN"})

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_support_ticket(
            run_id=str(uuid4()),
            order_id=None,
            category="AFTER_SALES_ESCALATION",
            reason_code="MANUAL_REVIEW_REQUIRED",
            evidence_summary="structured",
        )
    assert result.success is False
    assert result.error_code == "WRITE_TIMEOUT_UNKNOWN"
    assert result.data is None


@pytest.mark.asyncio
async def test_malformed_success_is_unknown_write_not_confirmed() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"ticketId": "ticket-001", "status": 27})

    async with _client(handler) as client:
        result = await CommerceTools(client=client, auth=_AUTH).create_support_ticket(
            run_id=str(uuid4()),
            order_id=None,
            category="AFTER_SALES_ESCALATION",
            reason_code="MANUAL_REVIEW_REQUIRED",
            evidence_summary="structured",
        )
    assert result.success is False
    assert result.error_code == "WRITE_TIMEOUT_UNKNOWN"


class FakeTickets:
    def __init__(self, envelope: ToolEnvelope[TicketResult]) -> None:
        self.envelope = envelope
        self.calls: list[dict[str, object]] = []

    async def create_support_ticket(self, **kwargs: object) -> ToolEnvelope[TicketResult]:
        self.calls.append(kwargs)
        return self.envelope


@pytest.mark.asyncio
async def test_graph_captures_real_ticket_and_only_then_escalates() -> None:
    tools = FakeTickets(
        ToolEnvelope[TicketResult](
            success=True,
            data=TicketResult(ticketId="ticket-001", status="OPEN"),
            latencyMs=4,
            traceId="java-ticket-trace",
        )
    )
    reports: list[object] = []
    lifecycle = build_lifecycle_nodes(tools, reports.append)
    state = _state()
    update = await lifecycle[Node.ESCALATE_OR_SAFE_STOP]({"state": state})
    assert update["state"].support_ticket_id == "ticket-001"
    assert update["state"].step_count == 5
    assert update["decision"].terminal is None
    assert len(reports) == 1
    assert reports[0].tool_name == "create_support_ticket"
    assert tools.calls[0]["run_id"] == str(state.run_id)
    assert tools.calls[0]["order_id"] == "order-001"
    summary = json.loads(str(tools.calls[0]["evidence_summary"]))
    assert summary["eligibility"] == "MANUAL_REVIEW"
    assert summary["evidence"][0]["facts"]["status"] == "IN_TRANSIT"
    assert "user_request" not in summary
    assert "token" not in str(summary).lower()
    ended = await lifecycle[Node.FINALIZE]({"state": update["state"]})
    assert ended["decision"].terminal.status is RunStatus.ESCALATED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "envelope",
    [
        ToolEnvelope[TicketResult](
            success=False, errorCode="ACCESS_DENIED", retryable=False, latencyMs=1
        ),
        ToolEnvelope[TicketResult](
            success=False, errorCode="WRITE_TIMEOUT_UNKNOWN", retryable=False, latencyMs=1
        ),
        ToolEnvelope[TicketResult](
            success=True, data=TicketResult(ticketId="ticket-x", status="CLOSED"), latencyMs=1
        ),
    ],
)
async def test_graph_never_claims_escalation_on_unconfirmed_ticket(
    envelope: ToolEnvelope[TicketResult],
) -> None:
    lifecycle = build_lifecycle_nodes(FakeTickets(envelope))
    update = await lifecycle[Node.ESCALATE_OR_SAFE_STOP]({"state": _state()})
    assert update["state"].support_ticket_id is None
    finished = await lifecycle[Node.FINALIZE]({"state": update["state"]})
    assert finished["decision"].terminal.status is RunStatus.SAFE_STOP
    assert finished["decision"].terminal.reason is SafeStopReason.MANUAL_REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_existing_authoritative_reference_does_not_issue_second_post() -> None:
    tools = FakeTickets(
        ToolEnvelope[TicketResult](
            success=True, data=TicketResult(ticketId="ticket-other", status="OPEN"), latencyMs=1
        )
    )
    state = _state().model_copy(update={"support_ticket_id": "ticket-001"})
    update = await build_lifecycle_nodes(tools)[Node.ESCALATE_OR_SAFE_STOP]({"state": state})
    assert tools.calls == []
    assert update["state"].support_ticket_id == "ticket-001"
