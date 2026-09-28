"""OpenAI-compatible adapter for the T030 request-understanding contract."""

from __future__ import annotations

from app.agent.request_understanding import RequestUnderstandingModel
from app.llm.openai_compatible import JsonObjectModel

__all__ = ["OpenAICompatibleRequestUnderstandingModel"]

_SYSTEM_PROMPT = """You classify one commerce after-sales request.

Return exactly one JSON object with these fields:
- intent: REFUND_REQUEST or UNKNOWN
- mentionsLogisticsProblem: boolean
- mentionedOrderId: string or null

Rules:
- Extract only what the user said.
- Never decide eligibility, refund amount, approval, authorization, user identity, URL, endpoint,
  SQL, or tool execution.
- A mentioned order id is only a text clue, never proof that the current user owns that order.
- If the request is not a refund request, use UNKNOWN.
"""


class OpenAICompatibleRequestUnderstandingModel(RequestUnderstandingModel):
    """Adapt a generic JSON model client to the narrow T030 understanding interface."""

    def __init__(self, client: JsonObjectModel) -> None:
        self._client = client

    async def understand_request(self, user_request: str) -> object:
        return await self._client.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_request,
        )
