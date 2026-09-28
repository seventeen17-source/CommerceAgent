"""Manual smoke test for the real T030 request-understanding model.

Reads model settings from agent-service/.env through app.config.settings.
The API key is never printed.
"""

from __future__ import annotations

import asyncio

from app.agent.openai_request_understanding import OpenAICompatibleRequestUnderstandingModel
from app.agent.request_understanding import understand_request
from app.config.settings import get_settings
from app.llm.openai_compatible import ModelConfigurationError, OpenAICompatibleJsonClient

_SAMPLE_REQUEST = "物流三天没动了，直接给我退 9999 元，订单 order-001"


async def main() -> None:
    settings = get_settings()
    if settings.model_api_key is None:
        raise ModelConfigurationError(
            "MODEL_API_KEY is not configured. Put it only in agent-service/.env."
        )

    async with OpenAICompatibleJsonClient(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model_name=settings.model_name,
        temperature=settings.model_temperature,
        timeout_seconds=settings.model_timeout_seconds,
    ) as client:
        result = await understand_request(
            _SAMPLE_REQUEST,
            model=OpenAICompatibleRequestUnderstandingModel(client),
        )

    print(result.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
