"""Inbound credential verification: prove a token is *well-formed*, never who it belongs to.

The decision this module encodes
--------------------------------
T018 asked for both a local signature check and the authoritative ``GET /me`` call. Those two do
different jobs, and conflating them is how an agent service ends up authorizing on a token claim:

* **Local verification** (here) answers "is this a token this project issued, unexpired and
  untampered?" It exists to fail fast: a forged or expired token costs one HMAC computation instead
  of a cross-service round trip.
* **Identity** answers "who is this, and what are they allowed to do today?" That is Java's answer
  alone. ``role`` and ``status`` are read from ``commerce.users`` on every request (T011), so a
  token minted before a role change must not carry the old role.

The distinction is enforced by the **type**, not by a comment. :class:`VerifiedCredential` has no
``user_id`` and no ``role`` field, and :func:`verify_credential` returns nothing but that. There is
therefore no value in this process from which a role could be read off a token: the wrong design is
a ``AttributeError`` / type-check failure, not a code-review finding.

Why this is not "just use the token's subject"
----------------------------------------------
The JWT ``sub`` does identify the user, and Java does verify the signature before trusting it. The
reason this service must not use it is *authority inversion*: if the Agent derived ``user_id`` from
a token locally, then every future bug that let a caller influence that token would become an
ownership bypass in the Agent's own storage. By asking Java, the Agent inherits Java's authority
instead of competing with it. The cost is one HTTP call per authenticated request; the benefit is
that there is exactly one place that decides identity.

Java analogy: Spring's resource server validates the token, but the controller still reads the
current user from the database-backed ``Authentication``. The analogy breaks in one place: Spring
does that inside one process, so the "authority" cannot be unreachable. Here it is a network call,
so this module must be explicit that a *verification failure* and a *Java outage* are different
outcomes -- see :class:`CredentialNotVerifiedError` versus
:class:`IdentityAuthorityUnavailableError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from app.config.settings import Settings

__all__ = [
    "AUTHORIZATION_HEADER",
    "CredentialError",
    "CredentialNotVerifiedError",
    "IdentityAuthorityUnavailableError",
    "MissingCredentialError",
    "VerifiedCredential",
    "extract_bearer_token",
    "verify_credential",
]

#: The only header this service reads a credential from.
AUTHORIZATION_HEADER = "Authorization"

#: ``Bearer <token>``, case-insensitive scheme as RFC 6750 requires.
_BEARER_SCHEME_PATTERN = re.compile(r"(?i)^bearer[ \t]+(\S+)$")

#: The HS256 algorithm this project's local fixture issuer uses. Pinned explicitly because
#: ``jwt.decode`` with ``algorithms=None`` would accept whatever the token's own header claims --
#: the classic ``alg`` confusion hole, where a token can declare ``none`` or switch RS256 to HS256
#: and have the public key treated as an HMAC secret.
_LOCAL_ALGORITHM = "HS256"


class CredentialError(Exception):
    """Base class for inbound-credential failures.

    Carries the two facts the HTTP layer needs -- ``status_code`` and ``error_code`` -- so any
    subclass can be mapped without enumerating subclasses. The base values are the fail-closed
    default: a new subclass that forgets to set them is a 503 (retry later), never a 200.
    """

    error_code: str = "DEPENDENCY_UNAVAILABLE"
    status_code: int = 503


class MissingCredentialError(CredentialError):
    """No usable ``Authorization: Bearer <token>`` header was present.

    401. This is a client contract violation, so it is safe and useful to say so plainly: there is
    no identity to leak and nothing to guess.
    """

    error_code = "AUTH_REQUIRED"
    status_code = 401

    def __init__(self) -> None:
        super().__init__("an Authorization: Bearer credential is required")


class CredentialNotVerifiedError(CredentialError):
    """The token failed verification: bad signature, wrong issuer, or expired.

    401, and deliberately coarse in what it tells the caller. ``reason`` is kept for the server log;
    the response says only that the credential was not accepted. Saying *which* check failed turns
    the endpoint into a token oracle -- "signature valid but expired" versus "signature invalid" is
    information an attacker uses, and it is not information a legitimate client needs (it can read
    its own token).
    """

    error_code = "AUTH_REQUIRED"
    status_code = 401

    def __init__(self, *, reason: str) -> None:
        super().__init__("the presented credential was not accepted")
        self.reason = reason


class IdentityAuthorityUnavailableError(CredentialError):
    """Local verification passed, but Java could not confirm the identity.

    503, **not** 401, and the distinction is the reason this class exists. The credential may be
    perfectly good; the authority that interprets it is unreachable. Returning 401 would tell a
    correctly-authenticated client "your token is bad" -- false, and unactionable, since it would
    send them to re-authenticate against a service that is down. Failing closed with 503 says
    "retry later", which is true.

    No run is created: without an authoritative principal there is nothing to scope it to.
    """

    error_code = "DEPENDENCY_UNAVAILABLE"
    status_code = 503

    def __init__(self, *, reason: str) -> None:
        super().__init__("the identity authority could not be reached")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class VerifiedCredential:
    """A credential that passed local verification.

    Fields are the *verification result only*: this credential is well-formed, issued by the
    expected issuer, unexpired as of ``verified_at``, and carries ``expires_at``. The ``subject`` is
    deliberately absent even though the JWT has one -- see the module docstring for why the local
    result must not be able to answer "who".

    The raw token is absent too. It travels as :class:`app.clients.auth.AuthContext`, whose
    ``SecretStr`` redacts itself in ``repr``/``str``; duplicating it here would create a second
    object that can be logged by accident.
    """

    issuer: str
    expires_at: datetime
    verified_at: datetime


def extract_bearer_token(header_value: str | None) -> str:
    """Pull the credential out of an ``Authorization`` header value.

    Raises:
        MissingCredentialError: absent, empty, not a Bearer scheme, or containing characters that
            cannot appear in a single-line header value. The last case is the interesting one: a
            token containing CR/LF would let a caller append headers to the *outbound* request this
            service makes to Java, so it is rejected here rather than trusted downstream.
    """
    if header_value is None or not header_value.strip():
        raise MissingCredentialError()

    match = _BEARER_SCHEME_PATTERN.fullmatch(header_value.strip())
    if match is None:
        raise MissingCredentialError()

    token = match.group(1)
    # Whitespace includes CR/LF and TAB; the scheme pattern already excluded them, but asserting it
    # here keeps the guarantee attached to the value rather than to the regex's readability.
    if any(character.isspace() for character in token):
        raise MissingCredentialError()
    return token


def verify_credential(token: str, settings: Settings) -> VerifiedCredential:
    """Verify a token locally, or raise.

    Four things are checked, and each one is a real bypass if omitted:

    1. **Signature** with the shared HS256 secret -- the token was issued by something holding it.
    2. **Algorithm pinned to HS256**. Never read the algorithm from the token.
    3. **Issuer** equals the configured one -- a token from another environment must not be accepted
       just because it happens to be signed with the same shared secret.
    4. **``exp`` present and in the future**. A JWT without ``exp`` is valid forever, so its absence
       is a failure, not a default. ``iat`` is *not* required: a missing ``iat`` degrades audit
       quality, it does not widen authority, and rejecting it would break tokens this project's own
       issuer could produce.

    Raises:
        CredentialNotVerifiedError: any of the above failed, including a malformed token.
    """
    try:
        claims = jwt.decode(
            token,
            settings.commerce_jwt_secret,
            algorithms=[_LOCAL_ALGORITHM],
            issuer=settings.commerce_jwt_issuer,
            options={
                # ``exp`` is required by policy, and ``verify_exp`` makes PyJWT enforce it.
                "require": ["exp", "iss"],
                "verify_exp": True,
                "verify_iss": True,
                "verify_signature": True,
                # Audience is not used by this project's issuer; requiring it would reject every
                # token Java mints. Stated explicitly so its absence is a decision, not a slip.
                "verify_aud": False,
            },
            leeway=settings.commerce_jwt_leeway_seconds,
        )
    except jwt.ExpiredSignatureError as exc:
        raise CredentialNotVerifiedError(reason="expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise CredentialNotVerifiedError(reason="unexpected issuer") from exc
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, malformed segments, missing required claims, disallowed algorithm.
        raise CredentialNotVerifiedError(reason=type(exc).__name__) from exc

    expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
    return VerifiedCredential(
        issuer=claims["iss"],
        expires_at=expires_at,
        verified_at=datetime.now(UTC),
    )
