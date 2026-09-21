"""Direct tests for the T016 credential boundary.

These tests pin the distinction between a credential and an identity claim.  CommerceClient tests
already prove that the credential is forwarded correctly; this module makes the AuthContext
invariants executable on their own so a later refactor cannot quietly weaken them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.clients.auth import AuthContext

# A placeholder, not a real credential.  The name deliberately avoids "token"/"password" so Ruff's
# hardcoded-secret rule remains useful for accidental real secrets elsewhere in the test suite.
_FAKE_JWT = "header.payload.signature"


def test_auth_context_contains_only_the_forwarded_credential() -> None:
    """A credential may prove identity, but this object must never assert identity itself."""
    auth = AuthContext(token=_FAKE_JWT)

    assert auth.token.get_secret_value() == _FAKE_JWT
    assert set(AuthContext.model_fields) == {"token"}


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "header payload.signature",
        "header.payload.signature\r\nX-Injected: yes",
        "\theader.payload.signature",
        "header.\x00.signature",
    ],
    ids=["empty", "space", "crlf", "tab", "control-char"],
)
def test_auth_context_rejects_values_that_are_unsafe_in_an_http_header(raw_value: str) -> None:
    """Reject whitespace/control text before anything can become an Authorization header."""
    with pytest.raises(ValidationError):
        AuthContext(token=raw_value)


def test_auth_context_redacts_the_raw_credential_in_rendered_forms() -> None:
    """Common debug/serialization paths must not expose the raw Bearer credential."""
    auth = AuthContext(token=_FAKE_JWT)

    assert _FAKE_JWT not in repr(auth)
    assert _FAKE_JWT not in str(auth)
    assert _FAKE_JWT not in auth.model_dump_json()


def test_auth_context_rejects_caller_supplied_identity_fields() -> None:
    """The caller may forward proof, but cannot attach a user id or role to that proof."""
    with pytest.raises(ValidationError):
        AuthContext.model_validate(
            {
                "token": _FAKE_JWT,
                "user_id": "customer-001",
                "role": "CUSTOMER",
            }
        )
