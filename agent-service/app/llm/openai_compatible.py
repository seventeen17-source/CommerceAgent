"""Minimal OpenAI-compatible JSON completion client for T030.

This layer owns only provider HTTP mechanics. It does not know AgentState, commerce identity,
business authorization, or Tool implementations. The API key is kept in an HTTP Authorization
header and is never returned from this module.
"""

from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import SecretStr

__all__ = [
    "JsonObjectModel",
    "ModelClientError",
    "ModelConfigurationError",
    "ModelResponseError",
    "OpenAICompatibleJsonClient",
]


class ModelClientError(RuntimeError):
    """Base error for model transport/protocol failures."""


class ModelConfigurationError(ModelClientError):
    """The model client cannot be created from the configured values."""


class ModelResponseError(ModelClientError):
    """The provider answered, but not with the JSON shape this adapter requires."""


class JsonObjectModel(Protocol):
    """Narrow provider-independent interface consumed by Agent understanding/routing code."""

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        """Return one JSON object and no provider-specific response wrapper."""
        ...


class OpenAICompatibleJsonClient:
    """Small async client for the OpenAI-compatible chat-completions JSON surface."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model_name: str,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise ModelConfigurationError("model base URL cannot be empty")
        if not model_name.strip():
            raise ModelConfigurationError("model name cannot be empty")
        if timeout_seconds <= 0:
            raise ModelConfigurationError("model timeout must be positive")

        self._model_name = model_name.strip()
        self._temperature = temperature
        self._client = httpx.AsyncClient(
            base_url=f"{normalized_base_url}/",
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )

    async def __aenter__(self) -> OpenAICompatibleJsonClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        """Request JSON mode and normalize the provider wrapper into one dict."""
        try:
            response = await self._client.post(
                "chat/completions",
                json={
                    "model": self._model_name,
                    "temperature": self._temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelClientError("model request failed") from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelResponseError("model response is missing message content") from exc

        if not isinstance(content, str):
            raise ModelResponseError("model message content must be a JSON string")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelResponseError("model message content is not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise ModelResponseError("model JSON output must be an object")
        return parsed
