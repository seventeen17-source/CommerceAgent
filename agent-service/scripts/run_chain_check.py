"""Serve the Agent API with a stub identity authority, for the T018 browser-chain check.

Why this exists instead of just running ``uvicorn app.main:app``
----------------------------------------------------------------
The browser chain (5173 → Vite proxy → 8000) needs the Agent API up, and the full chain also needs
Java on 8080 with a token this project can verify. Right now the real Java service accepts tokens
signed with the committed dev secret; whether it is running, and with which configuration, is an
environment fact this check should not depend on.

So this entry point builds the *same app* through the same factory, with two substitutions:

* the identity authority is a stub implementing the published ``GET /api/v1/me`` contract;
* the run store is the real ``PostgresRunStore``, because persistence is what the chain is proving.

Everything else -- routing, the router-level authentication dependency, local JWT verification,
ownership scoping, the contract shapes -- is production code. The substitutions are announced on
startup and the port is not the one a deployment uses, so this cannot be mistaken for the service.

Java analogy: a ``@SpringBootTest(webEnvironment = DEFINED_PORT)`` wired with a stubbed downstream
client. The analogy breaks on intent: this is not a test class, it is a runnable process, because
the thing under test is a *browser* talking to two servers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import uvicorn

from app.clients.commerce_client import CommerceClient
from app.config.settings import Settings as AgentSettings
from app.main import create_app
from app.trace.db import connection_factory_from_url
from app.trace.store import PostgresRunStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("t018-chain")

#: Users the stub authority knows, with the roles it will report. Mirrors the T014 fixture users, so
#: the page can be driven with a token minted for ``customer-001``.
_USERS = {"customer-001": "CUSTOMER", "customer-002": "CUSTOMER", "approver-001": "APPROVER"}


def _stub_authority(settings: AgentSettings) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return httpx.Response(
                401,
                json={
                    "errorCode": "AUTH_REQUIRED",
                    "message": "missing credential",
                    "retryable": False,
                    "traceId": "chain-stub-0001",
                },
            )
        try:
            claims = jwt.decode(
                authorization.removeprefix("Bearer "),
                settings.commerce_jwt_secret,
                algorithms=["HS256"],
                issuer=settings.commerce_jwt_issuer,
                options={"require": ["exp", "iss"]},
            )
        except jwt.InvalidTokenError as exc:
            logger.warning("stub authority rejected a token: %s", type(exc).__name__)
            return httpx.Response(
                401,
                json={
                    "errorCode": "AUTH_REQUIRED",
                    "message": "invalid credential",
                    "retryable": False,
                    "traceId": "chain-stub-0002",
                },
            )
        subject = claims["sub"]
        role = _USERS.get(subject)
        if role is None:
            return httpx.Response(
                403,
                json={
                    "errorCode": "ACCESS_DENIED",
                    "message": "unknown user",
                    "retryable": False,
                    "traceId": "chain-stub-0003",
                },
            )
        return httpx.Response(200, json={"userId": subject, "role": role})

    return httpx.MockTransport(handler)


def build_app() -> object:
    settings = AgentSettings()
    if settings.environment == "prod":
        raise SystemExit("refusing to run the chain check with ENVIRONMENT=prod")

    commerce_client = CommerceClient.from_settings(settings, transport=_stub_authority(settings))
    run_store = PostgresRunStore(connection_factory_from_url(settings.agent_database_url))
    logger.warning(
        "T018 chain check: identity authority is a STUB; run store is real (%s)",
        settings.postgres_db,
    )
    return create_app(settings, commerce_client=commerce_client, run_store=run_store)


def mint(user_id: str, settings: AgentSettings, *, minutes: int = 60) -> str:
    """A token for the stub authority, mirroring ``scripts/mint_dev_token.py``."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.commerce_jwt_issuer,
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(minutes=minutes),
        },
        settings.commerce_jwt_secret,
        algorithm="HS256",
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "mint":
        print(mint(sys.argv[2] if len(sys.argv) > 2 else "customer-001", AgentSettings()))
    else:
        uvicorn.run(build_app(), host="127.0.0.1", port=8000, log_level="info")
