"""FastAPI dependencies that turn a request into an authoritative principal.

The order of operations is the whole design, so it is stated once here and enforced by the types in
:mod:`app.security.credentials`:

1. **Extract** the Bearer credential from the ``Authorization`` header.
2. **Verify locally** -- signature, algorithm, issuer, expiry. A failure is 401 and Java is never
   called: this is the only thing local verification buys, and it is worth having, because a forged
   token should not be able to consume a round trip against the business backend.
3. **Authoritative lookup** -- send the *same credential* to Java ``GET /api/v1/me``. The identity
   that returns is the only one this service ever trusts.
4. **Resolve** the wire role through :func:`app.clients.identity.resolve_principal`, which denies an
   unrecognized role instead of guessing one.

Steps 2 and 3 are not redundant, and it is worth being precise about why: step 2 is a *credential*
check, step 3 is an *identity* check. A token can be perfectly signed and belong to a user who was
disabled one second ago, or whose role changed since it was minted. Only Java, reading
``commerce.users`` as of now, can answer that.

Where this sits in the framework
--------------------------------
This is a FastAPI dependency (``Depends``) -- the analogue of a Spring argument resolver or
``HandlerMethodArgumentResolver``: it runs before the handler, may raise, and hands the handler a
fully-formed value. The analogy breaks somewhere important: in Spring the ``SecurityFilterChain``
and the resolver together decide access *before* the controller is entered, so a controller cannot
be reached unauthenticated. FastAPI has no such filter chain by default, which means **an endpoint
that forgets to declare this dependency is simply unauthenticated**. That is why the run router
declares it at *router* level rather than per handler: the safe default has to be the one you get by
saying nothing special.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Header, HTTPException, Request
from pydantic import SecretStr

from app.agent.state import PrincipalContext
from app.clients.auth import AuthContext
from app.clients.errors import CommerceApiError, CommerceError, CommerceTransportError
from app.clients.identity import resolve_principal
from app.config.settings import Settings, get_settings
from app.security.credentials import (
    AUTHORIZATION_HEADER,
    CredentialError,
    CredentialNotVerifiedError,
    IdentityAuthorityUnavailableError,
    MissingCredentialError,
    extract_bearer_token,
    verify_credential,
)

if TYPE_CHECKING:
    # Imported for typing only, so the security layer does not gain a runtime dependency on the
    # persistence layer. The dependency direction T017 established stays one-way.
    from app.trace.store import RunStore

__all__ = [
    "AppSettings",
    "AuthenticatedCall",
    "SettingsDep",
    "authenticate",
    "get_run_store",
    "get_settings_from_app",
]

SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True, slots=True)
class AuthenticatedCall:
    """What an authenticated handler is given: a credential and an authoritative identity.

    Note what is **absent**: no token-derived user id, no token-derived role, no claims. A handler
    literally cannot authorize on a JWT claim, because no such value is in scope. That is the design
    decision from the module docstring made structural rather than advisory.

    ``auth`` carries the credential so the handler can forward it to Java (T016's rule: forward a
    credential, never assert an identity). ``principal`` carries the identity Java resolved.
    """

    auth: AuthContext
    principal: PrincipalContext


def get_settings_from_app(request: Request) -> Settings:
    """The settings this **app instance** was built with.

    Read off ``app.state``, not :func:`app.config.settings.get_settings`. That function is
    ``lru_cache``-ed, and ``Settings(...)`` bypasses the cache, so a process-cached read can
    disagree with the settings the rest of the app is using. This defect showed up **twice** before
    it was fixed properly: first as every authenticated request returning 401 (the router-level
    dependency verified tokens against the environment's issuer), then as a run created with
    ``max_steps=12`` while the app had been built with ``max_steps=5`` -- T015's "budgets are
    injected at creation" quietly not holding. One accessor, used by both dependencies and by
    handlers.

    The same reasoning applies to the run store and the commerce client below: one app, one
    configuration, read from one place.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        # Only reachable if an app was constructed without settings AND without a lifespan.
        return get_settings()
    return cast(Settings, settings)


def get_run_store(request: Request) -> RunStore:
    """The process-wide run store, created at startup and closed at shutdown.

    Read off ``app.state`` rather than constructed per request: the store holds no connection but is
    the process's single writer, and building one per request would let a second connection factory
    drift from the configured one. ``app/main.py``'s lifespan owns its lifecycle.

    The return type is the ``RunStore`` contract, not the concrete class: the API layer should
    depend on the interface it calls, and the ``TYPE_CHECKING`` import keeps this module free of a
    runtime dependency on the persistence layer.
    """
    store = getattr(request.app.state, "run_store", None)
    if store is None:
        # The lifespan did not run. That is a deployment fault, not a client fault, so 503 (retry
        # later) rather than 500 (a bug in the request).
        raise IdentityAuthorityUnavailableError(reason="run store is not initialised")
    return cast("RunStore", store)


def _http_error(exc: CredentialError) -> HTTPException:
    """Map a typed credential failure onto the status it means.

    ``status_code`` lives on the exception because the two cases differ in kind, not only in code:
    401 means "this credential is not acceptable", 503 means "the authority that would judge it is
    unreachable". Flattening them into 401 would send a correctly-authenticated client to
    re-authenticate against a service that is down.
    """
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return HTTPException(
        status_code=exc.status_code,
        detail=getattr(exc, "error_code", "AUTH_REQUIRED"),
        headers=headers,
    )


async def _resolve_authoritative_principal(request: Request, credential: str) -> PrincipalContext:
    """Ask Java who this credential belongs to, or refuse.

    The failure shapes are kept apart because the client's correct reaction differs:

    * Java answered ``401``/``403`` -- not acceptable *now* (disabled user, revoked session). That
      is a 401 for our caller as well: re-authenticating is the right move.
    * Java did not answer, or answered outside the error contract -- the identity is *unknown*. That
      is a 503. Reporting it as 401 would tell a correctly-authenticated caller their credential is
      bad, which is both false and unactionable.
    """
    client = getattr(request.app.state, "commerce_client", None)
    if client is None:
        raise IdentityAuthorityUnavailableError(reason="commerce client is not initialised")

    auth = AuthContext(token=SecretStr(credential))
    try:
        call = await client.get_principal(auth)
    except CommerceApiError as exc:
        if exc.http_status in (401, 403):
            raise CredentialNotVerifiedError(
                reason=f"identity authority rejected the credential ({exc.error_code})"
            ) from exc
        raise IdentityAuthorityUnavailableError(
            reason=f"commerce api error {exc.error_code}"
        ) from exc
    except CommerceTransportError as exc:
        raise IdentityAuthorityUnavailableError(reason=exc.reason) from exc
    except CommerceError as exc:  # pragma: no cover - defensive: keeps every path typed
        raise IdentityAuthorityUnavailableError(reason=type(exc).__name__) from exc

    # The only place a principal is constructed for an inbound request. `resolve_principal` fails
    # closed on an unknown role rather than defaulting to CUSTOMER.
    return resolve_principal(call.value)


async def authenticate(
    request: Request,
    authorization: Annotated[str | None, Header(alias=AUTHORIZATION_HEADER)] = None,
) -> AuthenticatedCall:
    """The single dependency every run endpoint declares.

    Declared at router level in ``app/api/runs.py`` so that a new endpoint without an explicit
    security declaration is still authenticated.
    """
    settings = get_settings_from_app(request)
    try:
        token = extract_bearer_token(authorization)
        verify_credential(token, settings)
        principal = await _resolve_authoritative_principal(request, token)
    except MissingCredentialError as exc:
        raise _http_error(exc) from exc
    except CredentialNotVerifiedError as exc:
        raise _http_error(exc) from exc
    except IdentityAuthorityUnavailableError as exc:
        raise _http_error(exc) from exc

    return AuthenticatedCall(auth=AuthContext(token=SecretStr(token)), principal=principal)


#: The settings of the app instance handling the request.
#:
#: Use this in handlers, **not** ``SettingsDep``. ``get_settings`` is ``lru_cache``-ed and
#: constructing ``Settings(...)`` bypasses the cache, so a handler that resolves through
#: ``get_settings`` can quietly use different values from the app it is serving. Defined here, after
#: :func:`get_settings_from_app`, because a ``Depends`` alias must reference a name that already
#: exists at import time.
AppSettings = Annotated[Settings, Depends(get_settings_from_app)]
