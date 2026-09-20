"""The credential this service forwards to the Java business API.

Why a type and not a bare ``str``
---------------------------------
T016 requires that the Bearer token comes from application context and can never reach the model
prompt, an ``AgentState`` checkpoint (T017) or a log line. A bare ``str`` cannot express that: it
interpolates into f-strings, ``repr`` and tracebacks unchanged, so the guarantee would rest on
every call site remembering to be careful. ``SecretStr`` redacts in ``repr``/``str`` and yields the
raw value only at the one place that writes the ``Authorization`` header.

Why there is no ``user_id`` field
---------------------------------
This object carries a *credential*, not an identity claim. ``userId`` and ``role`` are resolved by
Java from the verified JWT subject (``GET /api/v1/me``). If this object also carried a user id, a
caller -- or a bug, or model output relayed by a caller -- could assert an identity instead of
proving one, which is exactly the authority inversion the contract forbids. Keeping the field out
makes the wrong design unrepresentable rather than discouraged.

Java analogy: this is the token a ``RestClient`` exchange sets via
``headers.setBearerAuth(...)``, not Spring's ``Authentication`` object. The analogy breaks on where
identity comes from: Spring hands a controller an already-resolved ``@AuthenticationPrincipal``,
while this service is a *client* and must ask Java who the token belongs to.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

__all__ = ["AuthContext"]

# A JWT is base64url segments joined by dots; other opaque tokens stay inside this charset too.
# The point is what the charset excludes: whitespace, CR/LF and control characters. Header values
# are terminated by CRLF, so a token containing one could append extra headers to the request --
# the HTTP equivalent of SQL injection. Validating here means the client never has to trust that
# whoever built the context sanitized it.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]+$")


class AuthContext(BaseModel):
    """One caller's forwarded credential, valid for the calls made on their behalf."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: SecretStr

    @field_validator("token")
    @classmethod
    def reject_unsafe_token(cls, value: SecretStr) -> SecretStr:
        """Fail closed on a token that could not be put into a header safely."""
        if _TOKEN_PATTERN.fullmatch(value.get_secret_value()) is None:
            # The message must not echo the value: it is a credential, and this text can reach a
            # log line or an error response.
            raise ValueError("bearer token must be a non-empty single-line token")
        return value
