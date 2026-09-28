"""OpenAI-compatible adapter for T030 evidence routing."""

from __future__ import annotations

import json

from app.agent.evidence_routing import EvidenceDecisionModel, EvidenceRoutingContext
from app.llm.openai_compatible import JsonObjectModel

__all__ = ["OpenAICompatibleEvidenceDecisionModel"]

_SYSTEM_PROMPT = """You choose the next evidence step for a commerce after-sales Agent.

Return exactly one JSON object in one of these two forms:
{"action":"CALL_TOOL","tool":"get_logistics","reasonCode":"NEED_LOGISTICS_STATE"}
or
{"action":"READY_FOR_ELIGIBILITY","tool":null,"reasonCode":"ENOUGH_EVIDENCE_FOR_ELIGIBILITY"}

Rules:
- You only propose; you never execute a tool.
- Never decide refund eligibility, refund amount, approval, or authorization.
- Never invent another tool, endpoint, URL, SQL statement, user id, or order id.
- If logistics evidence is useful and LOGISTICS is not already observed, propose get_logistics.
- If enough evidence has already been collected, propose READY_FOR_ELIGIBILITY.
- READY_FOR_ELIGIBILITY means only hand off to deterministic Java eligibility evaluation.
"""


class OpenAICompatibleEvidenceDecisionModel(EvidenceDecisionModel):
    """Adapt the generic JSON model client to the narrow evidence-routing interface."""

    def __init__(self, client: JsonObjectModel) -> None:
        self._client = client

    async def decide_next_evidence(self, context: EvidenceRoutingContext) -> object:
        return await self._client.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                context.model_dump(by_alias=True, mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
