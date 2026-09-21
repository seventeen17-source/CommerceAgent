"""The secret-guard cannot silently rot: every ``AgentState`` field is probed.

Why a meta-test instead of more examples
----------------------------------------
The 2026-09-18 probe injected a credential into all 16 free-text fields of ``AgentState`` and found
that only 2 were protected -- not because someone wrote a bad regex, but because the check was
attached to *fields*, so a field added tomorrow gets no check at all and nothing goes red.

This module fixes the class of bug rather than the instance. It enumerates
``AgentState.model_fields`` at runtime, derives from each field's own annotation how a credential
could reach it, mutates a real checkpoint payload, and requires that the persistence-boundary guard
refuses it. A new field arrives with a case already written for it; there is no skip marker and no
exemption list.

Two levels, because they answer different questions
---------------------------------------------------
* **persistence boundary** -- "can this ever be written?". Probed by mutating
  ``model_dump(mode="json")`` and calling :func:`app.security.secrets.validate_persistable`, exactly
  as T017 does before an INSERT. Deliberately bypasses the model validator: a checkpoint restored
  through a raw dict or ``model_construct()`` never runs validators, so this is the realistic path
  and the one that must hold with no exemptions.
* **model construction** -- "is the object a node holds rejected early?". Weaker: a probe can also
  be rejected by a type or bounds rule, which is a rejection for the wrong reason and therefore
  claims no coverage here.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, get_args, get_origin
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.agent.state import (
    AgentState,
    ApprovalSnapshot,
    EligibilitySnapshot,
    EvidenceItem,
    PrincipalContext,
    PrincipalRole,
    RunStatus,
    ToolHistoryEntry,
    VerificationOutcome,
    VerificationStatus,
    WriteOutcome,
    WriteStatus,
)
from app.security.secrets import SensitiveStateError, validate_persistable

#: Returned by a mutation that cannot be expressed in the field's type at all (a key inside an
#: ``int``). Distinguished from "returned the value unchanged", which would be a silent gap.
_BANNED = object()

#: A structurally real JWT: header and payload are base64url JSON objects, which is what the
#: tightened rule requires. Deliberately not a character-count lookalike -- shape decides.
#:
#: The first version of this constant was hand-written and its header did not decode to JSON, so
#: the guard refused to call it a credential and 17 cases went red. That was the rule behaving
#: correctly: a lookalike that is not a credential is exactly what must not be rejected.
_JWT = (
    "eyJhbGciOiJIUzI1NiJ9."
    "eyJzdWIiOiJjdXN0b21lci0wMDEiLCJpc3MiOiJjb21tZXJjZWFnZW50LWxvY2FsIn0."
    "c2lnbmF0dXJlLXNpZ25hdHVyZS1zaWduYXR1cmU"
)
_BEARER = "Bearer sk-live-9f8e7d6c5b4a3210"

_CREDENTIAL_PROBES: tuple[tuple[str, str], ...] = (
    ("jwt", _JWT),
    ("bearer", _BEARER),
    ("bearer-wrapped-jwt", f"Bearer {_JWT}"),
)

_FORBIDDEN_KEY = "refresh_token"


def build_state(**overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "run_id": uuid4(),
        "principal": PrincipalContext(user_id="customer-001", role=PrincipalRole.CUSTOMER),
        "user_request": "My shipment has not moved for days. Can I get a refund?",
    }
    values.update(overrides)
    return AgentState.model_validate(values)


def build_populated_state() -> AgentState:
    """A state with **every** optional field filled in.

    The probe matrix needs a payload where every field already has a value, because an optional
    field left at its default gives the mutation nothing to inject into and makes the case vacuous.
    """
    return build_state(
        intent="LOGISTICS_REFUND",
        candidate_order_ids=["order-001", "order-002"],
        resolved_order_id="order-001",
        evidence=[
            EvidenceItem(
                evidence_type="LOGISTICS",
                source="get_logistics",
                data={"status": "IN_TRANSIT", "stalledHours": 120},
            )
        ],
        eligibility=EligibilitySnapshot(
            eligible=True,
            allowed_action="REFUND_ONLY",
            max_refund_amount=Decimal("199.00"),
            approval_required=False,
            rule_code="LOGISTICS_STALLED_REFUND",
            rule_version=1,
            reason_codes=["LOGISTICS_STALLED"],
        ),
        approval=ApprovalSnapshot(approval_request_id="approval-001", status="NOT_REQUIRED"),
        tool_history=[
            ToolHistoryEntry(
                step_index=0, tool_name="get_logistics", success=True, trace_id="trace-abc123"
            )
        ],
        step_count=1,
        write=WriteOutcome(
            status=WriteStatus.SUCCEEDED,
            action="CREATE_REFUND_REQUEST",
            resource_id="refund-001",
        ),
        verification=VerificationOutcome(
            status=VerificationStatus.VERIFIED_SUCCESS,
            resource_id="refund-001",
            details={"checked": "refund-001"},
        ),
    )


# ---------------------------------------------------------------------------------------------
# Classification: how could a credential reach this field, if at all?
# ---------------------------------------------------------------------------------------------

#: Fields a credential cannot even be expressed in. Not an exemption list: the probe matrix asserts
#: this classification is *mechanically true* by checking the annotation carries no ``str``.
_NON_TEXT_FIELDS = frozenset(
    {"run_id", "step_count", "max_steps", "retry_count", "max_retries", "status"}
)


def _carries_text(annotation: Any) -> bool:
    """Whether a credential could be represented anywhere inside this annotation."""
    if annotation is str:
        return True
    return any(_carries_text(arg) for arg in get_args(annotation))


def _field_names() -> list[str]:
    return sorted(AgentState.model_fields)


def test_non_text_classification_is_mechanically_true() -> None:
    """The only way to opt out of a probe is to be provably unable to hold one.

    If someone adds ``str`` to one of these annotations, this test goes red -- the classification
    cannot silently become a loophole.
    """
    wrongly_exempt = [
        name for name in _NON_TEXT_FIELDS if _carries_text(AgentState.model_fields[name].annotation)
    ]

    assert wrongly_exempt == [], f"fields classified as non-text can carry text: {wrongly_exempt}"


def test_every_text_bearing_field_has_a_credential_probe() -> None:
    """Collection guard: a new text field must arrive with a probe, not slip through unprobed."""
    unprobed = [
        name
        for name in _field_names()
        if _carries_text(AgentState.model_fields[name].annotation)
        and not any(kind.startswith("credential") for kind, _ in _probes_for(name))
    ]

    assert unprobed == [], f"text-bearing fields have no credential probe: {unprobed}"


def _mutation(label: str, apply: Callable[[Any], Any]) -> tuple[str, Callable[[Any], Any]]:
    """A named payload mutation. Named so a failure says *which* injection was not caught."""
    return label, apply


def _as_credential(value: Any, probe: str) -> Any:
    """Write the credential wherever text lives inside ``value``.

    Leaves that cannot hold text (``Decimal``, ``int``) are treated as an empty container: writing a
    credential there is caught by the *key* rule inside this wrapper, which is what keeps the case
    from being vacuous without pretending an int can hold a JWT.
    """
    if isinstance(value, str):
        return probe
    if isinstance(value, dict):
        return {key: _as_credential(nested, probe) for key, nested in value.items()}
    if isinstance(value, list):
        return [_as_credential(item, probe) for item in value]
    return {_FORBIDDEN_KEY: probe}


def _as_key_carrier(value: Any) -> Any:
    """Carry the key rule into nested dicts and lists."""
    if isinstance(value, dict):
        mutated = {key: _as_key_carrier(nested) for key, nested in value.items()}
        mutated[_FORBIDDEN_KEY] = "x"
        return mutated
    if isinstance(value, list):
        return [_as_key_carrier(item) for item in value]
    return {_FORBIDDEN_KEY: "x"}


def _add_forbidden_key(value: Any) -> Any:
    """Add a forbidden key at every dict level, or state that this field cannot hold one."""
    if isinstance(value, dict):
        return _as_key_carrier(value)
    if isinstance(value, list) and value:
        return [_as_key_carrier(item) for item in value]
    return _BANNED


def _probes_for(field_name: str) -> list[tuple[str, Callable[[Any], Any]]]:
    """Every way a credential could reach ``field_name``, as payload mutations.

    A credential probe exists only for a field that can hold text; the key probe exists only for a
    field that can hold a structure of keys. A scalar like ``step_count`` has neither, and no probe
    is invented for it -- the test asserts that absence explicitly instead.
    """
    annotation = AgentState.model_fields[field_name].annotation
    probes: list[tuple[str, Callable[[Any], Any]]] = []

    if _carries_text(annotation):
        probes.extend(
            _mutation(
                f"credential:{probe_name}",
                lambda current, probe=probe: _as_credential(current, probe),
            )
            for probe_name, probe in _CREDENTIAL_PROBES
        )

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        probes.append(_mutation("forbidden-key", _add_forbidden_key))
    elif get_origin(annotation) is dict:
        probes.append(_mutation("forbidden-key", _add_forbidden_key))
    elif get_origin(annotation) is list and _carries_text(annotation):
        probes.append(_mutation("forbidden-key", _add_forbidden_key))

    return probes


@pytest.mark.parametrize("field_name", _field_names(), ids=_field_names())
def test_persistence_boundary_rejects_credentials_in_any_field(field_name: str) -> None:
    """The assertion the T017 write path depends on: nothing that is credential-shaped can reach
    ``state_json``.

    The payload is mutated *after* a valid state was built, on purpose. Injecting through the
    constructor would only re-test the model validator; the leak this guards against arrives with a
    checkpoint restored as a raw dict, which is precisely the path that skips validation.
    """
    baseline = build_populated_state().model_dump(mode="json")
    applied = 0

    for kind, mutation in _probes_for(field_name):
        mutated = mutation(baseline[field_name])
        if mutated is _BANNED:
            assert kind == "forbidden-key", f"probe {kind} silently did not apply to {field_name}"
            continue

        payload = dict(baseline)
        payload[field_name] = mutated
        assert payload != baseline, f"probe {kind} left {field_name} unchanged"

        applied += 1
        with pytest.raises(SensitiveStateError) as error:
            validate_persistable(payload, "state")

        assert error.value.path.startswith("state")

    if _carries_text(AgentState.model_fields[field_name].annotation):
        assert applied > 0, f"no credential probe could be applied to {field_name}"


@pytest.mark.parametrize("field_name", _field_names(), ids=_field_names())
def test_model_construction_rejects_credentials_in_text_fields(field_name: str) -> None:
    """A credential is refused when it enters the object, not only when it is written.

    Weaker than the boundary test: any ``ValidationError`` passes, because a probe placed in an
    ``int`` field is rejected by the type rule rather than by this rule. That is still a rejection,
    but it is not *this* rule doing the work, so no coverage is claimed for non-text fields.
    """
    annotation = AgentState.model_fields[field_name].annotation
    probe: Any = [_JWT] if get_origin(annotation) is list else _JWT
    if not _carries_text(annotation):
        pytest.skip(f"{field_name} cannot carry a credential ({annotation})")

    with pytest.raises(ValidationError):
        build_state(**{field_name: probe})


def test_guard_detects_the_probes_and_not_ordinary_language() -> None:
    """Calibration: the probes are recognised, and normal text is not.

    The false positives below are the 2026-09-18 findings. The previous ``bearer\\s+[^\\s,;]+``
    pattern matched all six English sentences, because it detected the *word* bearer rather than a
    credential -- and that check was about to be applied to ``user_request``, i.e. to text a real
    customer types. Swapping a silent leak for "legitimate requests are refused" is not an
    improvement; it is a different outage with a worse debugging story.
    """
    for probe_name, probe in _CREDENTIAL_PROBES:
        with pytest.raises(SensitiveStateError):
            validate_persistable(probe, "state.user_request")
        assert probe_name

    ordinary_text = [
        "Please refund order 1001, I am the bearer of this account.",
        "The courier was the bearer of bad news.",
        "Is bearer token rotation required for this integration?",
        "Trace a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8 shows nothing.",
        "unknown.write.recovery",
        "LOGISTICS_STALLED_REFUND",
        "ORDER-2026-000123",
    ]
    for text in ordinary_text:
        validate_persistable(text, "state.user_request")


def test_guard_rejects_a_jwt_embedded_inside_ordinary_prose() -> None:
    """A credential pasted into a sentence is still a credential.

    This is the realistic leak: a customer pastes their token into the chat box while asking for
    help, or a tool result carries one inside a note field.
    """
    with pytest.raises(SensitiveStateError):
        validate_persistable(
            {"note": f"my token is {_BEARER} and it stopped working"},
            "state.evidence[0].data",
        )

    with pytest.raises(SensitiveStateError):
        validate_persistable(f"auth failed, used {_JWT} earlier", "state.user_request")


def test_guard_accepts_dotted_identifiers_that_are_not_credentials() -> None:
    """The usability half of the trade-off, pinned as a test.

    ``trace_id`` legitimately holds dotted identifiers. The rule keeps them because their segments
    do not decode to JSON. The documented cost: an identifier whose three segments are each >= 12
    base64url characters *and* whose first segment is JSON would be refused. That is rare, and the
    alternative -- a character-count rule -- refuses every dotted trace id, which is a false
    positive on a field the trace layer writes on every step.
    """
    for value in (
        "a1b2c3d4e5f6.a7b8c9d0e1f2.a3b4c5d6e7f8",
        "3f9a1c2d4e5b6a7c8d9e0f1a2b3c4d5e",
        "unknown.write.recovery",
        "my.shipment.has.not.moved",
        "ORDER-2026-000123",
    ):
        validate_persistable(value, "state.tool_history[0].trace_id")


def test_guard_rejects_forbidden_keys_at_any_depth() -> None:
    payload = {"evidence": [{"data": {"order": {"refresh_token": "x"}}}]}

    with pytest.raises(SensitiveStateError) as error:
        validate_persistable(payload, "state")

    assert "refresh_token" in error.value.path
    # The message must locate the problem without echoing the value.
    assert "x" not in str(error.value).replace("refresh_token", "")


def test_guard_survives_a_checkpoint_restored_as_a_raw_dict() -> None:
    """The reason the boundary call exists instead of relying on the model.

    A checkpoint restored with ``model_construct()`` -- or a raw dict fed straight back into a
    graph -- never runs validators; that is what ``model_construct`` is *for*. The boundary check is
    then the only defence, and this test pins that it holds for a field that carries no validator.
    """
    state = build_state()
    payload = state.model_dump(mode="json")
    payload["tool_history"] = [
        {
            "step_index": 0,
            "tool_name": "get_logistics",
            "success": True,
            "error_code": None,
            "retryable": False,
            "trace_id": _BEARER,
        }
    ]

    tampered = AgentState.model_construct(**payload)

    with pytest.raises(SensitiveStateError):
        validate_persistable(tampered.model_dump(mode="json"), "state")


def test_non_text_fields_have_no_credential_surface() -> None:
    """State plainly what the guarantee is for a field like ``step_count``.

    Nothing can be injected into an ``int``: a credential has no representation there, and the *key*
    rule is about structure, which a scalar does not have. So the honest claim is "no credential
    surface", not "a probe was rejected". Making that claim explicit means adding ``str`` to one of
    these annotations breaks the test instead of quietly widening the hole.
    """
    for field_name in sorted(_NON_TEXT_FIELDS):
        annotation = AgentState.model_fields[field_name].annotation
        assert not _carries_text(annotation), f"{field_name} became text-bearing: probe it"

        for kind, mutation in _probes_for(field_name):
            assert mutation(_placeholder_value(field_name)) is _BANNED or kind == "forbidden-key", (
                f"{field_name} unexpectedly accepts the {kind} probe"
            )


def _placeholder_value(field_name: str) -> Any:
    annotation = AgentState.model_fields[field_name].annotation
    if annotation is UUID:
        return str(uuid4())
    if annotation is RunStatus:
        return RunStatus.RUNNING.value
    return 0


def test_identifier_shape_rules_still_allow_real_values() -> None:
    """Tightening must not be a breaking change for the values the graph actually produces."""
    state = build_state(
        intent="LOGISTICS_REFUND",
        candidate_order_ids=["order-001", "ORDER-2026-000123"],
        resolved_order_id="order-001",
        status=RunStatus.WAITING_APPROVAL,
        verification=VerificationOutcome(
            status=VerificationStatus.VERIFIED_SUCCESS,
            details={"refund_id": "refund-001", "amount": Decimal("199.00")},
        ),
        evidence=[
            EvidenceItem(
                evidence_type="LOGISTICS", source="get_logistics", data={"stalledHours": 120}
            )
        ],
    )

    validate_persistable(state.model_dump(mode="json"), "state")
    assert state.is_terminal is False


def test_identifier_shape_rules_reject_control_characters() -> None:
    """A model-produced value must not smuggle a line break into a trace or a log line."""
    with pytest.raises(ValidationError):
        build_state(intent="LOGISTICS_REFUND\nforged-log-line")

    with pytest.raises(ValidationError):
        build_state(resolved_order_id="order-001\r\nX-Injected: 1")


def test_non_text_field_annotations_are_still_real() -> None:
    """Keep the classification honest: ``run_id`` really is a UUID, not a validated string."""
    annotation = AgentState.model_fields["run_id"].annotation

    assert annotation is UUID or UUID in get_args(annotation)
