"""Manual smoke test for the real T030 next-evidence model decision."""

from __future__ import annotations

import asyncio

from app.agent.evidence_routing import EvidenceRoutingContext, decide_next_evidence
from app.agent.openai_evidence_routing import OpenAICompatibleEvidenceDecisionModel
from app.config.settings import get_settings
from app.llm.openai_compatible import ModelConfigurationError, OpenAICompatibleJsonClient


async def main() -> None:
    settings = get_settings()
    if settings.model_api_key is None:
        raise ModelConfigurationError(
            "MODEL_API_KEY is not configured. Put it only in agent-service/.env."
        )

    context = EvidenceRoutingContext.model_validate(
        {
            "intent": "REFUND_REQUEST",
            "mentionsLogisticsProblem": True,
            "orderStatus": "SHIPPED",
            "observedEvidenceTypes": ["ORDER"],
        }
    )

    async with OpenAICompatibleJsonClient(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model_name=settings.model_name,
        temperature=settings.model_temperature,
        timeout_seconds=settings.model_timeout_seconds,
    ) as client:
        result = await decide_next_evidence(
            context,
            model=OpenAICompatibleEvidenceDecisionModel(client),
        )

    print(result.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
