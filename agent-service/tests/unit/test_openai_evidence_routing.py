"""T030 tests for the OpenAI-compatible next-evidence adapter."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.agent.evidence_routing import (
    EvidenceAction,
    EvidenceRoutingContext,
    decide_next_evidence,
)
from app.agent.openai_evidence_routing import OpenAICompatibleEvidenceDecisionModel
from app.llm.openai_compatible import OpenAICompatibleJsonClient


def _context(*, observed: list[str]) -> EvidenceRoutingContext:
    return EvidenceRoutingContext.model_validate(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "orderStatus": "SHIPPED",
            "observedEvidenceTypes": observed,
        }
    )


@pytest.mark.asyncio
async def test_adapter_sends_only_minimal_evidence_shape_to_model() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "CALL_TOOL",
                                    "tool": "get_logistics",
                                    "reasonCode": "NEED_LOGISTICS_STATE",
                                }
                            )
                        }
                    }
                ]
            },
        )

    async with OpenAICompatibleJsonClient(
        base_url="https://model.test/v1",
        api_key=SecretStr("unit-test-secret"),
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await decide_next_evidence(
            _context(observed=["ORDER"]),
            model=OpenAICompatibleEvidenceDecisionModel(client),
        )

    assert result.action is EvidenceAction.CALL_TOOL
    assert result.tool == "get_logistics"

    body = json.loads(seen[0].content)
    prompt = body["messages"][1]["content"]
    assert "\"intent\":\"REFUND_REQUEST\"" in prompt
    assert "\"orderStatus\":\"SHIPPED\"" in prompt
    assert "\"observedEvidenceTypes\":[\"ORDER\"]" in prompt
    assert "order-001" not in prompt
    assert "customer-001" not in prompt
    assert "unit-test-secret" not in prompt


@pytest.mark.asyncio
async def test_model_cannot_escape_evidence_capability_set() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "CALL_TOOL",
                                    "tool": "create_refund_request",
                                    "reasonCode": "NEED_LOGISTICS_STATE",
                                }
                            )
                        }
                    }
                ]
            },
        )

    async with OpenAICompatibleJsonClient(
        base_url="https://model.test/v1",
        api_key=SecretStr("unit-test-secret"),
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValidationError):
            await decide_next_evidence(
                _context(observed=["ORDER"]),
                model=OpenAICompatibleEvidenceDecisionModel(client),
            )


@pytest.mark.asyncio
async def test_model_can_handoff_to_deterministic_eligibility_without_deciding_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "READY_FOR_ELIGIBILITY",
                                    "tool": None,
                                    "reasonCode": "ENOUGH_EVIDENCE_FOR_ELIGIBILITY",
                                }
                            )
                        }
                    }
                ]
            },
        )

    async with OpenAICompatibleJsonClient(
        base_url="https://model.test/v1",
        api_key=SecretStr("unit-test-secret"),
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await decide_next_evidence(
            _context(observed=["ORDER", "LOGISTICS"]),
            model=OpenAICompatibleEvidenceDecisionModel(client),
        )

    assert result.action is EvidenceAction.READY_FOR_ELIGIBILITY
    assert result.tool is None
