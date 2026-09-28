"""T030 tests for the OpenAI-compatible model adapter."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.agent.openai_request_understanding import OpenAICompatibleRequestUnderstandingModel
from app.agent.request_understanding import RequestIntent, understand_request
from app.llm.openai_compatible import ModelResponseError, OpenAICompatibleJsonClient


@pytest.mark.asyncio
async def test_real_adapter_sends_json_mode_without_business_context() -> None:
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
                                    "intent": "REFUND_REQUEST",
                                    "mentionsLogisticsProblem": True,
                                    "mentionedOrderId": "order-001",
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
        result = await understand_request(
            "物流一直没到，帮我退 order-001",
            model=OpenAICompatibleRequestUnderstandingModel(client),
        )

    assert result.intent is RequestIntent.REFUND_REQUEST
    assert result.mentioned_order_id == "order-001"

    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer unit-test-secret"

    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][1] == {
        "role": "user",
        "content": "物流一直没到，帮我退 order-001",
    }
    serialized = request.content.decode()
    assert "customer-001" not in serialized
    assert "Authorization" not in serialized
    assert "eligible" not in serialized


@pytest.mark.asyncio
async def test_provider_json_still_passes_through_understood_request_guard() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "REFUND_REQUEST",
                                    "mentionsLogisticsProblem": True,
                                    "mentionedOrderId": "order-001",
                                    "eligible": True,
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
        with pytest.raises(Exception):
            await understand_request(
                "给我退款",
                model=OpenAICompatibleRequestUnderstandingModel(client),
            )


@pytest.mark.asyncio
async def test_invalid_provider_message_is_rejected_before_agent_state() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    async with OpenAICompatibleJsonClient(
        base_url="https://model.test/v1",
        api_key=SecretStr("unit-test-secret"),
        model_name="test-model",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ModelResponseError):
            await understand_request(
                "给我退款",
                model=OpenAICompatibleRequestUnderstandingModel(client),
            )
