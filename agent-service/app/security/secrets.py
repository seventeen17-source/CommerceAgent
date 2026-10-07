"""Persistence-boundary guard: no raw credential or hidden reasoning may ever be stored.

Why this module exists (and why it is *one* module)
---------------------------------------------------
Agent state and Agent trace are written to ``agent.agent_runs.state_json`` and
``agent.tool_executions``. Both are durable, both are read by Eval, and neither may ever contain a
raw JWT, a Bearer credential, a password, or hidden chain-of-thought. The rule that decides this
must exist **once**: a second copy is a second rule, and two rules drift. So ``app/agent/state.py``
(the object a node touches) and ``app/trace`` (the code that actually issues the INSERT) call the
same function in this module.

Why the check is fail-closed instead of a per-field allowlist
-------------------------------------------------------------
The first implementation hung the check on two fields only (``evidence.data`` and
``verification.details``). A probe that injected a credential into all 16 free-text fields of
``AgentState`` showed 26 of 32 injections sailed through -- and, worse, that a *new* field silently
gets no check at all. An allowlist rots as fields are added; a boundary check does not, because it
is attached to the operation (``persist this``) rather than to the schema.

Two rules, stated plainly
-------------------------
1. **One rule, two call sites.** The same :func:`validate_persistable` runs when a model is
   constructed *and* immediately before it is written. Calling it twice is cheap; having two
   implementations is what causes a leak.
2. **Detection must not be a false-positive machine.** Rejecting a legitimate request is also a
   failure -- it is just a failure that shows up as "the user was mysteriously refused", which is
   far more expensive to debug than a blocked token. The patterns below are therefore anchored to
   *credential-shaped* values rather than to a substring: the word "bearer" alone is not a
   credential, and neither is a dotted trace id.

What this module deliberately does NOT do
-----------------------------------------
It never rewrites, masks, or redacts a value. A sanitized trace would record something other than
what happened, which breaks the property that the structured trace alone can reconstruct the facts
of a failed run. A credential found at this boundary is a **defect**: the run stops with a reason
code instead of persisting a half-truth.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

__all__ = [
    "SensitiveStateError",
    "is_credential_shaped",
    "validate_persistable",
]

#: Key names that may never appear at any depth of a persisted structure. Matching is done on a
#: normalized form (lowercased, non-alphanumerics removed) so ``access_token``, ``accessToken`` and
#: ``ACCESS-TOKEN`` are one entry. Keep this list about *credentials and hidden reasoning*: adding
#: a business-sounding word here would reject legitimate structured facts.
_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "token",
        "rawtoken",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "bearertoken",
        "apikey",
        "api_key",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "privatekey",
        "cookie",
        "setcookie",
        "sessionid",
        "chainofthought",
        "cot",
        "reasoning",
        "internalreasoning",
        "hiddenreasoning",
        "rawprompt",
        "systemprompt",
        "internalprompt",
    }
)

#: ``Bearer <credential>`` where the credential is *shaped* like one. The trailing lookahead is
#: doing real work: without it the pattern is not a credential detector but "the document contains
#: the word bearer", and it rejected all six ordinary English sentences used as probes (``bearer
#: of``, ``bearer token``).
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}(?![A-Za-z0-9._~+/=-])")

#: Three dot-separated base64url segments. A *shape* test only -- see :func:`is_credential_shaped`,
#: which additionally requires both the header and the payload to decode to JSON objects.
_JWT_SHAPE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"
    r"(?![A-Za-z0-9_-])"
)

#: Minimum length of a base64url segment that still counts as credential-shaped. 12 rejects
#: ``a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8`` (the trace-id probe from the 2026-09-18 devlog)
#: while still matching every real JWT, whose segments are hundreds of characters.
_MIN_SEGMENT_LENGTH = 12

_PATH_SEPARATOR = "."


class SensitiveStateError(ValueError):
    """A value about to be persisted contains a credential or hidden reasoning.

    Raised at *construction* and again at the *persistence boundary*. The caller turns it into a
    ``SAFE_STOP`` with a reason code -- it must not be swallowed, because the alternative outcome is
    a durable copy of a secret.

    ``path`` is the location inside the structure (``tool_history[0].trace_id``); ``detail`` never
    echoes the offending value, because this text reaches logs and the run's ``error_code``.
    """

    #: Stable marker. Tests and callers match on this instead of on message wording.
    marker = "sensitive state content is not allowed"

    def __init__(self, *, path: str, detail: str) -> None:
        super().__init__(f"{self.marker} at {path}: {detail}")
        self.path = path
        self.detail = detail


def _normalize_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", key).lower()


def _base64url_segment_is_json_object(segment: str) -> bool:
    """Whether one JWT segment decodes (with or without padding) to a JSON object."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return False
    try:
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(decoded, dict)


def is_credential_shaped(value: str) -> bool:
    """Whether a string is, or contains, something credential-shaped.

    Kept public because the trace layer and its tests both need to state the rule in one place --
    "this string is a credential" should not be re-decided per call site.

    Two independent tests, cheapest first:

    1. ``Bearer <credential>``, where the credential part is itself credential-shaped;
    2. three dot-separated base64url segments whose **header and payload decode to JSON objects** --
       a structural test, not a character-count test.

    The second test is a deliberate trade-off, so state it rather than imply it is free. A dotted
    identifier whose segments are each 12+ characters *and* whose first segment happens to decode
    to a JSON object is refused. Real JWTs are recognised; dotted trace ids are not, because their
    segments are not JSON. The alternative -- a character-count rule -- refuses every dotted trace
    id, and the trace layer writes one on every step, so that false positive lands on the hot path.

    There is deliberately no matcher for "a hex blob of length N that might be an opaque token": no
    such credential exists in this system, and a speculative pattern over user-typed text is a
    false positive waiting to happen. Add one when a real token format exists, with a test for both
    sides.
    """
    if _BEARER_PATTERN.search(value) is not None:
        return True

    for match in _JWT_SHAPE_PATTERN.finditer(value):
        header, payload, _signature = match.group(0).split(_PATH_SEPARATOR, 2)
        if _base64url_segment_is_json_object(header) and _base64url_segment_is_json_object(payload):
            return True
    return False


def validate_persistable(value: Any, path: str) -> None:
    """Fail closed unless ``value`` is safe to write to durable storage.

    Walks ``dict`` / ``list`` / ``tuple`` / ``set`` / ``str``. Every other type is a scalar that
    cannot carry a credential in a form this check can recognise (numbers, bools, ``None``,
    ``UUID``, ``Decimal``, ``datetime``) and is left to the schema.

    Call this on ``model_dump(mode="json")``, not on ``model_dump()``: ``UUID`` and ``Decimal`` only
    become strings in JSON mode, and this walker only inspects strings. Validating a representation
    that is not the one you persist validates nothing.

    Raises:
        SensitiveStateError: a forbidden key name, or a credential-shaped string, at any depth.
    """
    if isinstance(value, dict):
        for key, nested in value.items():
            if _normalize_key(str(key)) in _FORBIDDEN_KEYS:
                raise SensitiveStateError(
                    path=f"{path}{_PATH_SEPARATOR}{key}",
                    detail="key name denotes a credential or hidden reasoning",
                )
            validate_persistable(nested, f"{path}{_PATH_SEPARATOR}{key}")
        return

    if isinstance(value, (list, tuple, set)):
        for index, nested in enumerate(value):
            validate_persistable(nested, f"{path}[{index}]")
        return

    if isinstance(value, str) and is_credential_shaped(value):
        # The value is never echoed: this text reaches logs and the run's error_code.
        raise SensitiveStateError(
            path=path,
            detail="value is shaped like an authentication credential",
        )
