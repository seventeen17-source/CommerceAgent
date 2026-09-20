"""Unit tests for the fail-closed wire-role to ``PrincipalRole`` mapping.

The whole point of ``app/clients/identity.py`` is one asymmetry: ``CurrentPrincipal.role`` must stay
open (Java owns the value set, so an additive role must not become a parse failure) while
authorization needs a closed set to branch on. These tests pin both halves of that asymmetry.
"""

from __future__ import annotations

import pytest

from app.agent.state import PrincipalRole
from app.clients.errors import UnknownPrincipalRoleError
from app.clients.identity import resolve_principal
from app.clients.models import CurrentPrincipal


@pytest.mark.parametrize(
    ("wire_role", "expected"),
    [
        ("CUSTOMER", PrincipalRole.CUSTOMER),
        ("APPROVER", PrincipalRole.APPROVER),
        ("SUPPORT", PrincipalRole.SUPPORT),
    ],
)
def test_known_roles_map_onto_the_closed_enum(wire_role: str, expected: PrincipalRole) -> None:
    context = resolve_principal(CurrentPrincipal(user_id="customer-001", role=wire_role))

    assert context.role is expected
    assert context.user_id == "customer-001"


@pytest.mark.parametrize(
    "wire_role",
    [
        # A role Java may legitimately add later: additive, not an error, but not authorizable here.
        "ADMIN",
        # Case differences are a different value. Normalizing them would accept something Java never
        # emitted, and then nobody could audit which value actually arrived.
        "customer",
        "Customer",
        # An empty-ish or padded value is not "probably CUSTOMER".
        " CUSTOMER",
        "CUSTOMER ",
    ],
)
def test_unrecognized_roles_are_denied_rather_than_guessed(wire_role: str) -> None:
    """No default role. Defaulting to ``CUSTOMER`` is how a privilege guess gets shipped."""
    with pytest.raises(UnknownPrincipalRoleError) as exc_info:
        resolve_principal(CurrentPrincipal(user_id="customer-001", role=wire_role))

    error = exc_info.value
    assert error.error_code == "ACCESS_DENIED"
    assert error.user_id == "customer-001"
    assert error.wire_role == wire_role


def test_denial_message_is_safe_to_log() -> None:
    """The wire role is remote input; the rendered form must not be able to forge a log line."""
    with pytest.raises(UnknownPrincipalRoleError) as exc_info:
        resolve_principal(CurrentPrincipal(user_id="u-1", role="ADMIN\r\nX-Injected: yes"))

    message = str(exc_info.value)
    assert "\r" not in message
    assert "\n" not in message
    assert len(message) < 200


def test_accepted_set_is_derived_from_the_enum() -> None:
    """Adding a ``PrincipalRole`` member must widen the mapping without editing ``identity.py``.

    If this test fails after adding an enum member, someone restated the value set by hand instead
    of deriving it -- which is how the two copies drift.
    """
    for role in PrincipalRole:
        assert resolve_principal(CurrentPrincipal(user_id="u-1", role=role.value)).role is role
