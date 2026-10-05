"""T018 acceptance: the HTTP chain, a browser-shaped request included.

What these tests can and cannot prove
-------------------------------------
They can prove the Agent API's own behaviour: authentication, ownership, the status codes, and that
a created run is really persisted. They cannot prove the *browser* leg -- a TestClient does not go
through Vite's dev proxy. That leg is verified separately by ``tests/e2e/test_browser_chain.py``
and, for a human, by the page at http://localhost:5173/.

Three layers of assertion, deliberately separated:

* ``test_credential_verification.py`` (unit) -- the verification rule, with no HTTP and no database.
* this file (integration) -- routing, dependencies, status codes, persistence, using the real
  ``PostgresRunStore`` against PostgreSQL and a real ``CommerceClient`` against a stub ``/me``.
* ``tests/e2e/`` -- the actual cross-process chain.

The stub-Java-not-mock-store choice matters: the store is the thing under test (a run must really be
written), while Java is an external authority whose *contract* we simulate. Mocking the store would
test the double; mocking Java tests our use of the published contract.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.agent.routing import Node
from app.agent.state import RunStatus
from app.config.settings import Settings
from app.main import create_app
from app.trace.checkpoint import Transition
from app.trace.db import ConnectionFactory, connection_factory_from_url
from app.trace.store import PostgresRunStore

#: A real HS256 secret for the test issuer. Not the committed placeholder, so a test that passes
#: proves verification works rather than that the default happened to match.
_TEST_SECRET = "t018-test-secret-not-the-dev-placeholder"
_TEST_ISSUER = "commerceagent-t018-test"

#: The authoritative users this stub Java knows about, keyed by the JWT subject.
_KNOWN_USERS: dict[str, str] = {"customer-001": "CUSTOMER", "customer-002": "CUSTOMER"}


def mint_token(
    subject: str,
    *,
    secret: str = _TEST_SECRET,
    issuer: str = _TEST_ISSUER,
    expires_in: timedelta = timedelta(minutes=5),
    algorithm: str = "HS256",
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"iss": issuer, "sub": subject, "iat": now, "exp": now + expires_in},
        secret,
        algorithm=algorithm,
    )


def stub_commerce_transport(*, known_users: dict[str, str] | None = None) -> httpx.MockTransport:
    """A stand-in for Java's ``GET /api/v1/me``.

    It implements the *published* part of the contract that T018 depends on: the bearer token
    alone determines the response, and the response carries ``userId``/``role``. Everything else
    about Java is out of scope here.

    A request without a Bearer token gets the error envelope, not a bare 401, because that is what
    T012 guarantees -- and ``_resolve_authoritative_principal`` branches on the envelope's status.
    """
    users = _KNOWN_USERS if known_users is None else known_users

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/me"):
            return httpx.Response(404, json={"errorCode": "NOT_FOUND"})
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return httpx.Response(
                401,
                json={
                    "errorCode": "AUTH_REQUIRED",
                    "message": "missing credential",
                    "retryable": False,
                    "traceId": "stub-trace-0001",
                },
            )
        # Verify the signature exactly as Java would, so a tampered token is rejected by the
        # authority rather than only by our local check. Otherwise a bug in the local check is
        # masked by this stub.
        try:
            claims = jwt.decode(
                authorization.removeprefix("Bearer "),
                _TEST_SECRET,
                algorithms=["HS256"],
                issuer=_TEST_ISSUER,
                options={"require": ["exp", "iss"]},
            )
        except jwt.InvalidTokenError:
            return httpx.Response(
                401,
                json={
                    "errorCode": "AUTH_REQUIRED",
                    "message": "invalid credential",
                    "retryable": False,
                    "traceId": "stub-trace-0002",
                },
            )
        subject = claims["sub"]
        role = users.get(subject)
        if role is None:
            return httpx.Response(
                403,
                json={
                    "errorCode": "ACCESS_DENIED",
                    "message": "unknown user",
                    "retryable": False,
                    "traceId": "stub-trace-0003",
                },
            )
        return httpx.Response(200, json={"userId": subject, "role": role})

    return httpx.MockTransport(handler)


@pytest.fixture(scope="session")
def db_factory() -> ConnectionFactory:
    """Reuse the T017 database fixture: these tests need the same V002 schema."""
    from tests.conftest import _database_url

    url = _database_url()
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version FROM agent.agent_runs LIMIT 0")
    except Exception as exc:  # any connection failure means "skip", by design
        pytest.skip(f"no T018-capable database at {url!r}: {exc}")
    return connection_factory_from_url(url)


class RecordingDriver:
    """A driver that advances nothing, so these tests stay about plumbing.

    It records what it was asked to advance, which is how "creating a run advances it" is asserted
    without a model, an LLM endpoint or a Java backend. The walk itself is covered elsewhere:
    against a real database in ``test_runtime_seam.py`` and against the real compiled graph in
    ``test_runtime.py``.

    ``check`` succeeds unconditionally, and that is the point of putting the precondition on the
    driver: only the real one needs a model credential, so a double has nothing to pretend.
    """

    def __init__(self) -> None:
        self.checks = 0
        self.advanced: list[Any] = []

    def check(self, settings: Settings) -> None:
        self.checks += 1

    async def run(self, request: Any, call: Any, session: Any, settings: Settings) -> Any:
        self.advanced.append(session.record)
        return session.record


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        commerce_jwt_issuer=_TEST_ISSUER,
        commerce_jwt_secret=_TEST_SECRET,
        agent_max_steps=5,
        agent_max_retries=1,
    )


@pytest.fixture
def client(settings: Settings, db_factory: ConnectionFactory) -> Iterator[TestClient]:
    """A TestClient running the **production** dependency chain against a stub Java authority.

    Nothing here replaces authentication: ``authenticate`` runs exactly as it does in production,
    including the local signature check and the call to ``GET /me``. Only the *transport* Java sits
    behind is stubbed (an ``httpx.MockTransport``), which is the honest boundary -- Java is an
    external authority whose published contract we simulate, while our own code stays under test.

    Configuration is passed into ``create_app`` rather than injected as a dependency override. An
    override cannot reach a router-level dependency's own sub-dependencies, which is how an earlier
    version of this fixture ended up verifying tokens with production settings while minting them
    with test ones -- every request 401, and the fake "fix" then hid the Java-outage path from the
    test that exists to check it.

    Every run a test creates is registered through :func:`create_run_via_api`, so teardown removes
    exactly those ids. (An even earlier version deleted every row whose
    ``user_id LIKE 'customer-%'`` -- destructive against a shared database, and exactly the kind of
    cleanup that turns a test suite into an incident.)
    """
    from app.clients.commerce_client import CommerceClient

    commerce_client = CommerceClient.from_settings(settings, transport=stub_commerce_transport())
    driver = RecordingDriver()
    app = create_app(
        settings,
        commerce_client=commerce_client,
        run_store=PostgresRunStore(db_factory),
        run_driver=driver,
    )

    created: list[UUID] = []
    with TestClient(app) as test_client:
        test_client.created_run_ids = created  # type: ignore[attr-defined]
        test_client.run_driver = driver  # type: ignore[attr-defined]
        yield test_client

    store = PostgresRunStore(db_factory)
    for run_id in created:
        store.delete_run(run_id)


def create_run_via_api(
    client: TestClient,
    *,
    subject: str = "customer-001",
    message: str = "my shipment has not moved for days, can I get a refund?",
    token: str | None = None,
) -> dict[str, Any]:
    """POST a run and return the parsed body, registering the id for teardown.

    The single place tests create runs, so cleanup cannot be forgotten by a new test -- and so the
    "create" call the tests make is always the same shape as the one the browser makes.
    """
    response = client.post(
        "/api/v1/agent/runs",
        json={"message": message},
        headers=auth_header(token or mint_token(subject)),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    client.created_run_ids.append(UUID(body["runId"]))  # type: ignore[attr-defined]
    return body


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------------------------


def test_creating_a_run_advances_it_immediately(client: TestClient) -> None:
    """The contract publishes no "execute" endpoint, so this call is a run's only way to start."""
    body = create_run_via_api(client)

    driver = client.run_driver  # type: ignore[attr-defined]
    assert driver.checks == 1
    assert len(driver.advanced) == 1
    assert str(driver.advanced[0].run_id) == body["runId"]


def test_the_run_view_publishes_the_facts_and_not_a_success_claim(client: TestClient) -> None:
    """T033: a run that has not been verified must not look like one that has."""
    body = create_run_via_api(client)

    assert isinstance(body["version"], int)
    assert body["checkpointCompactedAt"] is None
    # This driver advances nothing, so nothing has been verified and no refund id may appear.
    assert body["verificationStatus"] == "NOT_RUN"
    assert body["verifiedRefundRequestId"] is None
    assert body["finalMessage"] is None
    assert body["approvalRequestId"] is None


def waiting_run(client: TestClient, db_factory: ConnectionFactory) -> dict[str, Any]:
    """A run parked in ``WAITING_USER``, as the graph leaves it when a human has to answer.

    Created through the API and then interrupted through the store, because both entry points under
    test accept *only* an interrupted run - that restriction is the state's, not this test's.
    """
    body = create_run_via_api(client)
    store = PostgresRunStore(db_factory)
    record = store.get_run(UUID(body["runId"]))
    store.transition(
        record.run_id,
        Transition(
            expected_version=record.version,
            status=RunStatus.WAITING_USER,
            trigger="INTERRUPT",
            current_node="resolve_order",
            next_action="await_clarification",
        ),
    )
    return body


def test_supplying_clarification_advances_the_waiting_run(
    client: TestClient, db_factory: ConnectionFactory
) -> None:
    """``/input`` claims the run, merges the follow-up, then drives it."""
    body = waiting_run(client, db_factory)
    driver = client.run_driver  # type: ignore[attr-defined]
    before = len(driver.advanced)

    response = client.post(
        f"/api/v1/agent/runs/{body['runId']}/input",
        json={"message": "订单 order-001"},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 200, response.text
    assert len(driver.advanced) == before + 1
    payload = PostgresRunStore(db_factory).get_run(UUID(body["runId"])).to_state()
    assert payload is not None
    # The merged request is durable *before* the graph reads it: a clarification that lived only in
    # this request's memory would be invisible to the next resume.
    assert payload.user_request.endswith("订单 order-001")
    assert "follow-up" in payload.user_request


def test_resuming_a_waiting_run_advances_it(
    client: TestClient, db_factory: ConnectionFactory
) -> None:
    body = waiting_run(client, db_factory)
    driver = client.run_driver  # type: ignore[attr-defined]
    before = len(driver.advanced)

    response = client.post(
        f"/api/v1/agent/runs/{body['runId']}/resume",
        json={},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 200, response.text
    assert len(driver.advanced) == before + 1


def test_durable_positions_use_the_graphs_own_node_names(
    client: TestClient, db_factory: ConnectionFactory
) -> None:
    """A run row must not describe a graph that does not exist.

    The vocabulary is owned by the graph. If the row says "understand_request" while the graph's
    node is "understand", every later reader - a debugging session, an eval, a trace viewer - is
    looking at a position nothing can resolve.
    """
    body = create_run_via_api(client)
    assert body["nextAction"] == Node.UNDERSTAND.value

    store = PostgresRunStore(db_factory)
    record = store.get_run(UUID(body["runId"]))
    assert record.next_action == Node.UNDERSTAND.value

    store.transition(
        record.run_id,
        Transition(
            expected_version=record.version,
            status=RunStatus.WAITING_USER,
            trigger="INTERRUPT",
            current_node=Node.WAITING_USER.value,
            next_action=Node.UNDERSTAND.value,
        ),
    )
    supplied = client.post(
        f"/api/v1/agent/runs/{body['runId']}/input",
        json={"message": "订单 order-001"},
        headers=auth_header(mint_token("customer-001")),
    )
    assert supplied.status_code == 200, supplied.text
    assert supplied.json()["nextAction"] == Node.UNDERSTAND.value

    # /resume needs its own parked run: the one above is RUNNING after /input claimed it.
    second = create_run_via_api(client)
    second_record = store.get_run(UUID(second["runId"]))
    store.transition(
        second_record.run_id,
        Transition(
            expected_version=second_record.version,
            status=RunStatus.WAITING_USER,
            trigger="INTERRUPT",
            current_node=Node.WAITING_USER.value,
            next_action=Node.UNDERSTAND.value,
        ),
    )
    resumed = client.post(
        f"/api/v1/agent/runs/{second['runId']}/resume",
        json={},
        headers=auth_header(mint_token("customer-001")),
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["nextAction"] == Node.UNDERSTAND.value

    # Every position written so far must be a real member of the graph vocabulary.
    stored = PostgresRunStore(db_factory).get_run(UUID(body["runId"]))
    assert stored.next_action in {node.value for node in Node}


def test_a_new_run_records_the_runtime_version_that_produced_it(
    client: TestClient, db_factory: ConnectionFactory
) -> None:
    """The row answers 'which runtime was this?', so it must not still say t018-skeleton-v1."""
    body = create_run_via_api(client)

    record = PostgresRunStore(db_factory).get_run(UUID(body["runId"]))
    assert record.prompt_version == "t032-us1-runtime-v1"
    assert "t018-skeleton" not in record.prompt_version


def test_a_follow_up_that_cannot_fit_leaves_the_run_waiting(
    client: TestClient, db_factory: ConnectionFactory
) -> None:
    """Refusing *after* claiming would leave a claimed run with nothing to drive it."""
    body = waiting_run(client, db_factory)
    driver = client.run_driver  # type: ignore[attr-defined]
    before = len(driver.advanced)

    response = client.post(
        f"/api/v1/agent/runs/{body['runId']}/input",
        json={"message": "x" * 4000},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "USER_REQUEST_TOO_LONG"
    assert (
        PostgresRunStore(db_factory).get_run(UUID(body["runId"])).status is RunStatus.WAITING_USER
    )
    assert len(driver.advanced) == before


def test_create_run_requires_a_credential(client: TestClient) -> None:
    response = client.post("/api/v1/agent/runs", json={"message": "refund please"})
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["detail"] == "AUTH_REQUIRED"


def test_create_run_rejects_a_forged_signature(client: TestClient) -> None:
    """Signed with the wrong secret: rejected locally, before Java is asked."""
    forged = mint_token("customer-001", secret="a-different-secret-entirely")

    response = client.post(
        "/api/v1/agent/runs", json={"message": "refund please"}, headers=auth_header(forged)
    )

    assert response.status_code == 401


def test_create_run_rejects_an_expired_token(client: TestClient) -> None:
    expired = mint_token("customer-001", expires_in=timedelta(minutes=-5))

    response = client.post(
        "/api/v1/agent/runs", json={"message": "refund please"}, headers=auth_header(expired)
    )

    assert response.status_code == 401


def test_create_run_rejects_a_token_from_another_issuer(client: TestClient) -> None:
    """A token signed with the right secret but issued elsewhere must not be accepted.

    This is the check that stops a staging token from working in production when both environments
    were configured from the same shared secret.
    """
    wrong_issuer = mint_token("customer-001", issuer="some-other-environment")

    response = client.post(
        "/api/v1/agent/runs", json={"message": "refund please"}, headers=auth_header(wrong_issuer)
    )

    assert response.status_code == 401


def test_create_run_rejects_a_role_claim_it_should_not_trust(client: TestClient) -> None:
    """A token claiming ``role: APPROVER`` must not gain anything by saying so.

    The stub authority decides roles, exactly as Java does from ``commerce.users``. A privilege
    escalation that only exists in the token's own claims cannot survive that -- and the request
    body has no role field either.
    """
    now = datetime.now(UTC)
    escalating = jwt.encode(
        {
            "iss": _TEST_ISSUER,
            "sub": "customer-001",
            "role": "APPROVER",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    response = client.post(
        "/api/v1/agent/runs",
        json={"message": "approve my own refund"},
        headers=auth_header(escalating),
    )

    # 201: the request is legitimate *as customer-001*. The point is that the APPROVER claim changed
    # nothing -- had it been trusted, the run would have been created as an approver.
    assert response.status_code == 201
    assert response.json()["runId"]


def test_identity_authority_outage_is_503_not_401(client: TestClient) -> None:
    """Java unreachable must not tell the caller their credential is bad.

    The distinction matters operationally: 401 sends a correctly-authenticated client to
    re-authenticate against a service that is down, and hides the real incident from monitoring that
    alerts on 5xx.
    """

    def exploding(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    from app.clients.commerce_client import CommerceClient

    client.app.state.commerce_client = CommerceClient.from_settings(  # type: ignore[attr-defined]
        client.app.state.settings,
        transport=httpx.MockTransport(exploding),  # type: ignore[attr-defined]
    )

    response = client.post(
        "/api/v1/agent/runs",
        json={"message": "refund please"},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "DEPENDENCY_UNAVAILABLE"


# --------------------------------------------------------------------------------------------
# Creation and persistence
# --------------------------------------------------------------------------------------------


def test_create_run_persists_the_authoritative_principal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/runs",
        json={"message": "my shipment has not moved for days, can I get a refund?"},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["stepCount"] == 0
    assert body["version"] == 1
    # The response carries no principal, no token and no state payload: none of them belong in a
    # body the browser renders.
    assert "principal" not in body
    assert "state" not in body

    # The run is really in the database, owned by the id Java returned -- not by anything from the
    # request body, which has no identity field at all.
    store = client.app.state.run_store  # type: ignore[attr-defined]
    record = store.get_run(UUID(body["runId"]))
    assert record.user_id == "customer-001"
    assert record.state is not None
    assert record.state.principal.role.value == "CUSTOMER"
    # The configured budgets were injected at creation and persisted with the run (T015's rule: a
    # restored checkpoint keeps the budgets it was created with).
    assert record.state.max_steps == 5
    assert record.state.max_retries == 1


def test_create_run_rejects_an_identity_in_the_body(client: TestClient) -> None:
    """There is no field to smuggle a user id into, and the model refuses extra keys."""
    response = client.post(
        "/api/v1/agent/runs",
        json={"message": "refund please", "userId": "customer-002"},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 422


def test_create_run_rejects_an_empty_message(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/runs",
        json={"message": ""},
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------------------------
# Ownership: the point of the whole task
# --------------------------------------------------------------------------------------------


def test_owner_can_read_their_own_run(client: TestClient) -> None:
    created = create_run_via_api(client)

    response = client.get(
        f"/api/v1/agent/runs/{created['runId']}", headers=auth_header(mint_token("customer-001"))
    )

    assert response.status_code == 200
    assert response.json()["runId"] == created["runId"]


def test_another_customer_cannot_read_the_run_and_is_told_403(client: TestClient) -> None:
    """Ownership is enforced in SQL, and the refusal is honest.

    The published contract exposes a 403 for this endpoint, so the store's owner-scoped miss is
    disambiguated into 403 (exists, not yours) versus 404 (nothing there). A caller who is not the
    owner must not be able to read the run's state.
    """
    created = create_run_via_api(client)

    response = client.get(
        f"/api/v1/agent/runs/{created['runId']}", headers=auth_header(mint_token("customer-002"))
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "RUN_FORBIDDEN"


def test_another_customer_cannot_resume_the_run(client: TestClient) -> None:
    """A stranger cannot advance someone else's run, and cannot learn its status by trying."""
    created = create_run_via_api(client)

    response = client.post(
        f"/api/v1/agent/runs/{created['runId']}/resume",
        headers=auth_header(mint_token("customer-002")),
    )

    assert response.status_code == 403


def test_unknown_run_is_404(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/agent/runs/{UUID(int=0)}", headers=auth_header(mint_token("customer-001"))
    )

    assert response.status_code == 404


def test_malformed_run_id_is_404_not_500(client: TestClient) -> None:
    """``runId`` is typed as a plain string by the contract, so this is reachable."""
    response = client.get(
        "/api/v1/agent/runs/not-a-uuid", headers=auth_header(mint_token("customer-001"))
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------------------------
# State validity is a different answer from authorization
# --------------------------------------------------------------------------------------------


def test_resuming_a_running_run_is_409(client: TestClient) -> None:
    """The owner is allowed; the run's state is not. That is 409, not 403."""
    created = create_run_via_api(client)

    response = client.post(
        f"/api/v1/agent/runs/{created['runId']}/resume",
        headers=auth_header(mint_token("customer-001")),
    )

    assert response.status_code == 409
    # RUNNING is not a resume target: it belongs to a live executor.
    assert response.json()["detail"] == "STATUS_NOT_WAITING"


def test_events_and_trace_are_owner_scoped_and_return_the_timeline(client: TestClient) -> None:
    created = create_run_via_api(client)

    events = client.get(
        f"/api/v1/agent/runs/{created['runId']}/events",
        headers=auth_header(mint_token("customer-001")),
    )
    trace = client.get(
        f"/api/v1/agent/runs/{created['runId']}/trace",
        headers=auth_header(mint_token("customer-001")),
    )
    stranger = client.get(
        f"/api/v1/agent/runs/{created['runId']}/trace",
        headers=auth_header(mint_token("customer-002")),
    )

    assert events.status_code == 200
    # The creation checkpoint is itself a timeline entry, which is why a run created one second ago
    # already has one event.
    assert events.json()[0]["eventType"] == "STATE_TRANSITION"
    assert events.json()[0]["status"] == "RUNNING"
    assert trace.status_code == 200
    assert stranger.status_code == 403


def test_every_run_endpoint_requires_a_credential(client: TestClient) -> None:
    """A forgotten ``Depends`` on any one endpoint would be an unauthenticated endpoint.

    Enumerated rather than sampled, because the risk is precisely "one of them was missed", and the
    router-level dependency is the control that this test verifies rather than the per-handler one.
    """
    run_id = UUID(int=1)
    unauthenticated = [
        ("post", "/api/v1/agent/runs"),
        ("get", f"/api/v1/agent/runs/{run_id}"),
        ("get", f"/api/v1/agent/runs/{run_id}/events"),
        ("get", f"/api/v1/agent/runs/{run_id}/trace"),
        ("post", f"/api/v1/agent/runs/{run_id}/input"),
        ("post", f"/api/v1/agent/runs/{run_id}/resume"),
    ]

    for method, path in unauthenticated:
        # GET must not be given a body: the point is only that an unauthenticated request never
        # reaches the handler, whatever its payload.
        request_kwargs: dict[str, Any] = {} if method == "get" else {"json": {"message": "x"}}
        response = getattr(client, method)(path, **request_kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} was reachable unauthenticated"


def test_health_reports_configuration_without_the_secret(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["jwt_secret_configured"] is True
    assert _TEST_SECRET not in response.text
