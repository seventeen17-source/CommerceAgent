"""Fail-closed mapping from Java's wire role to this service's ``PrincipalRole``.

``CurrentPrincipal.role`` is an open string on the wire because Java owns the value set
(``UserRole.java`` plus the ``commerce.users`` CHECK constraint) and an additive backend role must
not become a parse failure. Authorization, on the other hand, needs an exhaustive set to branch on.
Both hold if the translation happens exactly once, at the boundary, here.

Three rules, each of which is a real incident when broken:

1. **Never infer.** There is no default role. Defaulting to ``CUSTOMER`` looks harmless until an
   unrecognized value inherits it and a write path opens on a guess.
2. **Never normalize.** Case-insensitive matching would accept ``customer``, which Java does not
   emit. A value that "probably means" something is a value that cannot be audited.
3. **Deny loudly and machine-readably.** The caller gets ``UnknownPrincipalRoleError`` carrying
   the stable ``ACCESS_DENIED`` code, so the run ends as ``SAFE_STOP``/``ESCALATED`` with a reason
   and an audit record instead of surfacing as an unhandled 500.

The accepted set is *derived* from ``PrincipalRole`` rather than restated, so this service still
holds exactly one copy of it (T015's enum). Adding a member there widens this mapping automatically
-- and the resulting diff is the review point, which is the purpose of deriving it.

Consumer: T018 (``app/security/``) verifies the JWT locally, forwards it to ``GET /me``, then calls
:func:`resolve_principal` to build the ``PrincipalContext`` stored in ``AgentState``.
"""

from __future__ import annotations

from app.agent.state import PrincipalContext, PrincipalRole
from app.clients.errors import UnknownPrincipalRoleError
from app.clients.models import CurrentPrincipal

__all__ = ["resolve_principal"]

#: Derived from the enum on purpose -- not a fourth hand-written copy of the value set.
_WIRE_TO_ROLE: dict[str, PrincipalRole] = {role.value: role for role in PrincipalRole}


def resolve_principal(principal: CurrentPrincipal) -> PrincipalContext:
    """Translate an authoritative ``/me`` response into this service's identity type.

    Raises:
        UnknownPrincipalRoleError: if Java returned a role this service cannot authorize. The run
            must stop; it must not fall back to a guessed role.
    """
    role = _WIRE_TO_ROLE.get(principal.role)
    if role is None:
        raise UnknownPrincipalRoleError(user_id=principal.user_id, wire_role=principal.role)
    return PrincipalContext(user_id=principal.user_id, role=role)
