"""Agent Service HTTP entry point.

What the lifespan owns, and why it is not "just setup"
-----------------------------------------------------
Two long-lived objects are created here and closed on shutdown, and both choices are deliberate:

* **One ``CommerceClient`` for the process.** It holds an ``httpx.AsyncClient`` -- a connection
  pool. Building one per request would discard every pooled connection and, worse, would make it
  easy for a second instance to be configured differently (a different base URL, a different
  timeout) so that "the Agent's view of the authority" stopped being one thing.
* **One ``PostgresRunStore`` for the process.** It holds no connection of its own, only the factory,
  so sharing is safe and no transaction can be pinned open between requests.

Both are attached to ``app.state`` and read by dependencies (``app/security/dependencies.py``),
rather than being module-level globals. That is the difference between "one per process" and "one
per import": a module global would also be shared by every *test* in a session, so a test could not
point the app at its own database or a mock transport.

Java analogy: this is the ``@Configuration`` class that declares singleton beans and their
``@PreDestroy``. The analogy breaks on ceremony -- there is no container to scan, so the wiring is
explicit and the failure mode is "the attribute is missing" (which
``get_run_store``/``get_commerce_client`` report as a 503) rather than a context-refresh error.

Health endpoint
---------------
``/health`` reports whether the *configuration* needed to authenticate is present, without ever
returning a secret. A service that silently runs with a default signing key looks healthy until
someone forges a token, so "is a real secret configured?" is a fact an operator needs.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.runs import router as runs_router
from app.clients.commerce_client import CommerceClient
from app.config.settings import Settings, get_settings
from app.trace.db import connection_factory_from_url
from app.trace.store import PostgresRunStore

__all__ = ["create_app", "lifespan"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire the process-wide collaborators, then tear them down.

    Everything created here is created *before* the first request can be served, so a handler never
    has to cope with a half-initialised app. The teardown releases the HTTP pool; the run store
    needs no teardown because it holds no connection.

    Settings are taken from ``app.state`` when they are already there, and only otherwise from
    :func:`get_settings`. Collaborators are treated the same way: an app that was handed a commerce
    client or a run store keeps it. That is what makes "build an app with test collaborators" work
    at all -- in Starlette the lifespan *runs* when a ``TestClient`` enters its context, so without
    these guards an app pre-wired for a test would have its client replaced a moment later and the
    test would silently talk to whatever the environment points at. (It did: the suite reached a
    real Java process on :8080 and every authenticated request came back 401.)
    """
    settings: Settings | None = getattr(app.state, "settings", None)
    if settings is None:
        settings = get_settings()

    commerce_client = getattr(app.state, "commerce_client", None)
    if commerce_client is None:
        commerce_client = CommerceClient.from_settings(settings)
    run_store = getattr(app.state, "run_store", None)
    if run_store is None:
        run_store = PostgresRunStore(connection_factory_from_url(settings.agent_database_url))

    app.state.settings = settings
    app.state.commerce_client = commerce_client
    app.state.run_store = run_store
    logger.info(
        "agent-service started: commerce_api=%s jwt_issuer=%s real_secret_configured=%s",
        settings.commerce_api_base_url,
        settings.commerce_jwt_issuer,
        settings.is_jwt_secret_configured,
    )
    try:
        yield
    finally:
        await commerce_client.aclose()
        logger.info("agent-service stopped")


def create_app(
    settings: Settings | None = None,
    *,
    commerce_client: CommerceClient | None = None,
    run_store: PostgresRunStore | None = None,
) -> FastAPI:
    """Build the ASGI application.

    A factory rather than a module-level ``app``, and it takes its collaborators as parameters. Why
    the parameters matter: the first version of this factory built everything from
    :func:`~app.config.settings.get_settings`, which is process-cached, so a test that wanted a
    different issuer had to reach in through ``app.dependency_overrides`` -- and that silently does
    not work for a router-level dependency such as ``authenticate``, because it resolves its own
    sub-dependencies. The app then verified tokens with the production settings while the test
    minted them with its own, and every authenticated request came back 401.

    Passing the configuration in makes "which settings is this app using" a question with one
    answer. Production calls ``create_app()`` and gets the environment; a test passes its own and
    gets them, including through the router-level dependency, with no shadow copy of the security
    logic.

    An injected ``commerce_client`` / ``run_store`` is used as-is rather than rebuilt, so a test can
    supply a stub authority or a store pointed at its own database.
    """
    app = FastAPI(
        title="CommerceAgent Agent Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    if settings is not None:
        app.state.settings = settings
    if commerce_client is not None:
        app.state.commerce_client = commerce_client
    if run_store is not None:
        app.state.run_store = run_store

    app.include_router(runs_router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    async def health(request: Request) -> dict[str, object]:
        """Liveness plus the one configuration fact that silently breaks authentication.

        Reports ``jwt_secret_configured`` (a boolean) and never the secret. A defaulting secret is
        the failure this surfaces: the service accepts tokens it should not, and looks fine until
        someone notices.

        Settings are read off ``app.state`` rather than from :func:`get_settings`, because that
        function is process-cached: reading it here would report the settings of whichever caller
        touched it first, so a test (or a future embedded app) would see someone else's
        configuration. Reported facts must come from the app's own wiring.
        """
        active: Settings = getattr(request.app.state, "settings", None) or get_settings()
        return {
            "status": "ok",
            "service": active.app_name,
            "environment": active.environment,
            "jwt_secret_configured": active.is_jwt_secret_configured,
        }

    return app


app = create_app()
