"""Unit tests for inbound credential verification.

Why these are separate from the HTTP tests
-----------------------------------------
The HTTP tests prove the API refuses a bad credential. These prove *which rule* refused it, which is
what matters when the answer is "the token was fine but the configuration was not" -- a class of bug
that looks identical from the outside. They also run in milliseconds, so the awkward cases (a token
with no ``exp``, a token declaring ``alg: none``) get tested rather than skipped for being slow.

The security property under test is deliberately narrow: :func:`verify_credential` establishes that
a credential is *well-formed*. These tests assert it never establishes anything about *identity* --
see ``test_verified_credential_carries_no_identity``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest

from app.config.settings import Settings
from app.security.credentials import (
    CredentialNotVerifiedError,
    MissingCredentialError,
    VerifiedCredential,
    extract_bearer_token,
    verify_credential,
)

_SECRET = "unit-test-secret-different-from-the-dev-placeholder"
_ISSUER = "commerceagent-unit-test"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        commerce_jwt_issuer=_ISSUER,
        commerce_jwt_secret=_SECRET,
        commerce_jwt_leeway_seconds=0,
    )


def token(
    *,
    secret: str = _SECRET,
    issuer: str = _ISSUER,
    algorithm: str = "HS256",
    expires_in: timedelta | None = timedelta(minutes=5),
    include_iat: bool = True,
    subject: str = "customer-001",
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {"iss": issuer, "sub": subject}
    if expires_in is not None:
        claims["exp"] = now + expires_in
    if include_iat:
        claims["iat"] = now
    return jwt.encode(claims, secret, algorithm=algorithm)


# --------------------------------------------------------------------------------------------
# The happy path, and what it deliberately does not return
# --------------------------------------------------------------------------------------------


def test_a_valid_token_verifies(settings: Settings) -> None:
    verified = verify_credential(token(), settings)

    assert isinstance(verified, VerifiedCredential)
    assert verified.issuer == _ISSUER
    assert verified.expires_at > datetime.now(UTC)


def test_verified_credential_carries_no_identity() -> None:
    """The structural guarantee: there is nothing to authorize *from* here.

    This is the assertion that makes the local-check-plus-``/me`` design safe rather than merely
    convenient. If a future change added a ``user_id`` or ``role`` field to
    :class:`VerifiedCredential`, a caller could start authorizing on it -- and the whole point of
    asking Java is that a token claim is not an authorization decision.
    """
    fields = set(VerifiedCredential.__dataclass_fields__)

    assert fields == {"issuer", "expires_at", "verified_at"}
    assert "user_id" not in fields
    assert "role" not in fields
    assert "subject" not in fields


# --------------------------------------------------------------------------------------------
# Every way a credential can be wrong
# --------------------------------------------------------------------------------------------


def test_a_token_signed_with_another_secret_is_refused(settings: Settings) -> None:
    with pytest.raises(CredentialNotVerifiedError):
        verify_credential(token(secret="a-completely-different-secret"), settings)


def test_an_expired_token_is_refused(settings: Settings) -> None:
    with pytest.raises(CredentialNotVerifiedError) as error:
        verify_credential(token(expires_in=timedelta(minutes=-1)), settings)

    assert error.value.reason == "expired"


def test_a_token_from_another_issuer_is_refused(settings: Settings) -> None:
    """Right secret, wrong environment: this is the staging-token-in-production case."""
    with pytest.raises(CredentialNotVerifiedError) as error:
        verify_credential(token(issuer="some-other-environment"), settings)

    assert error.value.reason == "unexpected issuer"


def test_a_token_without_an_expiry_is_refused(settings: Settings) -> None:
    """A JWT without ``exp`` is valid forever, so its absence is a failure and not a default.

    This is the case a naive ``jwt.decode`` accepts silently, which is why ``require`` is set.
    """
    with pytest.raises(CredentialNotVerifiedError):
        verify_credential(token(expires_in=None), settings)


def test_a_token_without_an_issuer_is_refused(settings: Settings) -> None:
    with pytest.raises(CredentialNotVerifiedError):
        verify_credential(token(issuer=""), settings)


def test_the_algorithm_cannot_be_taken_from_the_token(settings: Settings) -> None:
    """``alg: none`` must not be honoured.

    The classic JWT hole: a decoder that trusts the header's ``alg`` will accept an unsigned token
    declaring ``none``. Pinning the algorithm list is the fix, and this test is what keeps the pin.
    """
    unsigned = jwt.encode({"iss": _ISSUER, "sub": "customer-001"}, key="", algorithm="none")

    with pytest.raises(CredentialNotVerifiedError):
        verify_credential(unsigned, settings)


def test_a_malformed_token_is_refused_rather_than_crashing(settings: Settings) -> None:
    for malformed in ("", "not-a-jwt", "a.b", "a.b.c.d", "...."):
        with pytest.raises((CredentialNotVerifiedError, MissingCredentialError)):
            verify_credential(malformed, settings)


def test_a_token_without_iat_still_verifies(settings: Settings) -> None:
    """``iat`` is not required: its absence degrades audit quality, not authority.

    Stated as a test because it is a deliberate decision. Rejecting a missing ``iat`` would be
    defensible, but it would also reject a token this project's own issuer could produce, and the
    field carries no authorization meaning.
    """
    verified = verify_credential(token(include_iat=False), settings)

    assert verified.issuer == _ISSUER


def test_leeway_tolerates_small_clock_skew_only() -> None:
    """Two machines never share a clock exactly; the tolerance is seconds, not minutes."""
    tolerant = Settings(
        environment="test",
        commerce_jwt_issuer=_ISSUER,
        commerce_jwt_secret=_SECRET,
        commerce_jwt_leeway_seconds=30,
    )
    strict = Settings(
        environment="test",
        commerce_jwt_issuer=_ISSUER,
        commerce_jwt_secret=_SECRET,
        commerce_jwt_leeway_seconds=0,
    )
    just_expired = token(expires_in=timedelta(seconds=-10))

    # Within the leeway it is accepted; with no leeway it is not. Same token, different tolerance.
    verify_credential(just_expired, tolerant)
    with pytest.raises(CredentialNotVerifiedError):
        verify_credential(just_expired, strict)


# --------------------------------------------------------------------------------------------
# Header extraction
# --------------------------------------------------------------------------------------------


def test_bearer_header_is_parsed_case_insensitively() -> None:
    """RFC 6750 makes the scheme case-insensitive, and clients do send ``bearer``."""
    for header in ("Bearer abc.def.ghi", "bearer abc.def.ghi", "BEARER abc.def.ghi"):
        assert extract_bearer_token(header) == "abc.def.ghi"


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "   ",
        "abc.def.ghi",  # no scheme
        "Basic abc.def.ghi",  # wrong scheme
        "Bearer",  # no credential
        "Bearer ",  # empty credential
    ],
)
def test_a_missing_or_malformed_authorization_header_is_a_401(header: str | None) -> None:
    with pytest.raises(MissingCredentialError):
        extract_bearer_token(header)


def test_control_characters_in_the_credential_are_refused() -> None:
    """A CR/LF in the token would let a caller append headers to our outbound Java request.

    This is the HTTP equivalent of SQL injection, and it is checked here rather than relied on
    downstream -- the outbound header is built by this project's own code.
    """
    with pytest.raises(MissingCredentialError):
        extract_bearer_token("Bearer abc\r\nX-Injected: 1")


def test_the_error_message_does_not_echo_the_credential() -> None:
    """Messages reach log lines, so a credential must not survive into one."""
    secret_looking = "super-secret-token-value"

    with pytest.raises(MissingCredentialError) as error:
        extract_bearer_token(f"Bearer {secret_looking}\r\nX-Injected: 1")

    assert secret_looking not in str(error.value)
