"""Node implementations for the T032 graph: the interpret-and-resolve stage.

Each node does exactly three things: spend one step of budget, call one already-accepted capability,
and return a rebuilt state plus the control-plane facts the router needs. Nodes never retry, never
pick the next node, and never write durable state - persistence is the graph wrapper's job (T032
Step 3), so that it happens at node boundaries instead of inside business logic.

Nothing here is model-decided: the model's output is validated into a narrow schema before it
touches a field, and the only field it can influence is the untrusted `user_request` interpretation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from json import dumps
from typing import Protocol

from app.agent.approval_execution import ApprovalTools, request_human_approval
from app.agent.eligibility_execution import (
    US1_ELIGIBILITY_REASON_CODE,
    EligibilityTools,
)
from app.agent.eligibility_execution import (
    check_eligibility as run_eligibility_check,
)
from app.agent.evidence_execution import EvidenceReadTools, execute_read_evidence
from app.agent.evidence_routing import (
    EvidenceDecisionModel,
    build_evidence_routing_context,
    decide_next_evidence,
    guard_evidence_proposal,
)
from app.agent.execute_write import (
    CREATE_RETURN_ACTION,
    INTENT_NOT_DURABLE_ERROR_CODE,
    RefundWriteTools,
    ReturnWriteTools,
    execute_refund_write,
    execute_return_write,
    refund_write_intent,
    return_write_intent,
    write_may_already_have_committed,
)
from app.agent.failure_policy import may_retry_read
from app.agent.graph import GraphNode, GraphState, GraphUpdate
from app.agent.order_resolution import OrderReadTools, resolve_single_order
from app.agent.request_understanding import RequestUnderstandingModel, understand_request
from app.agent.routing import (
    RETURN_PERMITTING_ACTIONS,
    Decision,
    Node,
    SafeStopReason,
    TerminalDecision,
    eligibility_handoff,
    safe_stop_reason_for,
    terminal_decision_for,
)
from app.agent.state import AgentState, RunStatus, ToolHistoryEntry, WriteIntent, WriteOutcome, advance
from app.agent.tool_tracing import TraceSink, report_tool_call
from app.agent.verify_business_state import (
    AfterSalesReadTools,
    verify_refund_business_state,
    verify_return_business_state,
)
from app.tools.models import ToolEnvelope
from app.clients.models import TicketResult
from app.tools.registry import ToolRegistry

__all__ = [
    "GraphDeps",
    "PersistWriteIntent",
    "build_approval_nodes",
    "build_evidence_nodes",
    "build_lifecycle_nodes",
    "build_read_nodes",
    "build_write_nodes",
    "spend_one_step",
]

#: Persist the write intent **before** the request is sent, and hand back the state that now carries
#: it. The graph nodes only need the contract, which is why this is a parameter rather than an
#: import: the durability implementation belongs to whoever owns `RunStore`.
type PersistWriteIntent = Callable[[AgentState, WriteIntent, WriteOutcome], Awaitable[AgentState]]


class WriteTools(RefundWriteTools, ReturnWriteTools, Protocol):
    """Both write capabilities, satisfied by the one authenticated Tool object.

    Kept as a single dependency rather than two fields because in production it *is* one object
    (``CommerceTools``): splitting it would invite a second place for the credential to be bound and
    a second place for it to drift. Each write node still calls only its own tool, so the reach
    stays visible exactly where it matters.
    """


@dataclass(frozen=True, slots=True)
class GraphDeps:
    """Everything a read-stage node may call.

    Explicit rather than global so a node's reach is visible in one place, and so tests can pass
    doubles that fail loudly if a node touches a dependency its stage has no business touching.
    """

    understanding: RequestUnderstandingModel
    orders: OrderReadTools
    evidence_model: EvidenceDecisionModel
    evidence: EvidenceReadTools
    registry: ToolRegistry
    eligibility: EligibilityTools
    approvals: ApprovalTools
    writes: WriteTools
    after_sales: AfterSalesReadTools
    persist_intent: PersistWriteIntent
    #: Where a finished Tool call is reported. Optional so the dev harnesses and unit tests can
    #: build these nodes without a store; production always wires one, because ``build_agent_graph``
    #: will not build without it.
    record_trace: TraceSink | None = None


def spend_one_step(state: AgentState) -> AgentState:
    """Charge the step budget for entering a node.

    Routers check the budget *before* entering, so this cannot exceed ``max_steps``. If it ever does
    - a restored state from an older, more permissive version, say - ``advance()`` raises instead of
    letting the run continue unbudgeted.
    """
    return advance(state, step_count=state.step_count + 1)


def build_read_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the interpret-and-resolve nodes bound to ``deps``."""

    async def understand(graph: GraphState) -> GraphUpdate:
        """Interpret the request into a narrow schema and record the order-id clue, if any.

        ``mentioned_order_id`` lands in ``candidate_order_ids``, never in ``resolved_order_id``: a
        model-supplied id is a clue about which order to ask Java about, not authority over it.
        """
        state = spend_one_step(graph["state"])
        understood = await understand_request(state.user_request, model=deps.understanding)
        clue = understood.mentioned_order_id
        if clue is None:
            moved = advance(state, intent=understood.intent.value)
        else:
            moved = advance(
                state,
                intent=understood.intent.value,
                candidate_order_ids=[clue],
            )
        # The interpretation is carried in the control plane, not the payload: it is re-derived on
        # resume and must never sit next to authoritative facts as if it were one.
        return GraphUpdate(state=moved, decision=Decision(), understood=understood)

    async def resolve_order(graph: GraphState) -> GraphUpdate:
        """Ask Java which single order this request is about, or record why we cannot say."""
        state = spend_one_step(graph["state"])
        understood = graph.get("understood")
        if understood is None:
            # No interpretation in this invocation. Rebuilding one from the payload alone would mean
            # inventing the fields it does not carry, so the run refuses instead of guessing.
            return GraphUpdate(
                state=state,
                decision=Decision(
                    resolution_attempted=True,
                    safe_stop_reason=SafeStopReason.ORDER_UNRESOLVED,
                ),
                resolution=None,
            )

        resolution = await resolve_single_order(
            understood,
            tools=deps.orders,
            step_index=state.step_count,
            record_trace=deps.record_trace,
        )
        history = [*state.tool_history, *resolution.history]
        if resolution.resolved_order_id is None:
            moved = advance(
                state,
                candidate_order_ids=list(resolution.candidate_order_ids),
                # The flag travels with the candidates: the router must ask about the clue rather
                # than count candidates, because a zero match can fall back to a single order.
                clue_matched_nothing=resolution.clue_matched_nothing,
                tool_history=history,
            )
        else:
            moved = advance(
                state,
                candidate_order_ids=list(resolution.candidate_order_ids),
                clue_matched_nothing=resolution.clue_matched_nothing,
                resolved_order_id=resolution.resolved_order_id,
                tool_history=history,
            )
        return GraphUpdate(
            state=moved,
            decision=Decision(resolution_attempted=True),
            resolution=resolution,
        )

    return {Node.UNDERSTAND: understand, Node.RESOLVE_ORDER: resolve_order}


def build_evidence_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the evidence loop: propose one read, authorize it, execute it.

    The two nodes are split on purpose. ``decide_evidence`` touches the model and no business
    resource; ``execute_evidence`` touches Java and no model. Keeping them apart is what makes "what
    the model proposed" and "what was actually read" separately observable in the trace - merged
    into one node, a denied proposal and a failed read would look identical from outside.
    """

    async def decide_evidence(graph: GraphState) -> GraphUpdate:
        """Ask the model what evidence would help, then let the deterministic guard decide."""
        state = spend_one_step(graph["state"])
        understood = graph.get("understood")
        resolution = graph.get("resolution")
        order = resolution.order if resolution is not None else None
        if understood is None or order is None:
            # Routing needs the interpretation and the authoritative order snapshot, and both are
            # invocation control-plane facts. Rebuilding them here would mean calling a capability
            # that belongs to another node, so the run refuses instead of inventing context.
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )

        context = build_evidence_routing_context(understood, order=order, evidence=state.evidence)
        proposal = await decide_next_evidence(context, model=deps.evidence_model)
        guard = guard_evidence_proposal(
            proposal,
            resolved_order_id=state.resolved_order_id,
            observed_evidence_types={item.evidence_type for item in state.evidence},
            registry=deps.registry,
        )
        return GraphUpdate(state=state, decision=Decision(guard=guard))

    async def execute_evidence(graph: GraphState) -> GraphUpdate:
        """Execute the authorized read, then report the facts the router needs.

        A failed read **never enters ``evidence``** - that slot holds observed facts, and a failure
        is not one. It is recorded in ``tool_history`` instead, so "we tried and it failed" stays
        visible without ever being mistaken for evidence.

        Which failures are worth another attempt comes from the failing layer, not from us: a
        ``retryable`` failure is transient and is retried while the run's retry budget allows, while
        anything else is Java's considered answer and no amount of retrying changes it.

        This node makes **no routing decision**. It reports two facts - whether the attempt
        succeeded, and whether this evidence path is now closed - and ``route_after_decision``
        decides where that leads. Only the router has to change if the topology does.
        """
        state = spend_one_step(graph["state"])
        decision = graph.get("decision")
        guard = decision.guard if decision is not None else None
        if guard is None or state.resolved_order_id is None:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )

        result = await execute_read_evidence(
            guard,
            resolved_order_id=state.resolved_order_id,
            step_index=state.step_count,
            tools=deps.evidence,
            record_trace=deps.record_trace,
        )
        history = [*state.tool_history, result.history]
        if result.evidence is None:
            if may_retry_read(result.history, state):
                # Consume the run's retry budget and report that another attempt is warranted. The
                # router sends the run back to *this* node with the same authorized read, so a
                # transient failure costs no model call to re-reach the same conclusion.
                moved = advance(state, retry_count=state.retry_count + 1, tool_history=history)
                return GraphUpdate(
                    state=moved, decision=Decision(guard=guard, retry_current_stage=True)
                )
            moved = advance(state, tool_history=history)
            return GraphUpdate(
                state=moved,
                decision=Decision(guard=guard, evidence_path_closed=True),
            )

        moved = advance(
            state,
            tool_history=history,
            evidence=[*state.evidence, result.evidence],
        )
        return GraphUpdate(state=moved, decision=Decision(guard=guard))

    return {Node.DECIDE_EVIDENCE: decide_evidence, Node.EXECUTE_EVIDENCE: execute_evidence}


def build_approval_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the T053 HITL handoff: create authority, then park the run."""

    async def request_approval(graph: GraphState) -> GraphUpdate:
        state = spend_one_step(graph["state"])
        snapshot = state.eligibility
        if state.resolved_order_id is None or snapshot is None:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )
        if not snapshot.eligible or not snapshot.approval_required:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.ELIGIBILITY_INCONSISTENT),
            )

        try:
            result = await request_human_approval(
                run_id=state.run_id,
                resolved_order_id=state.resolved_order_id,
                eligibility=snapshot,
                step_index=state.step_count,
                tools=deps.approvals,
                record_trace=deps.record_trace,
            )
        except ValueError:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.ELIGIBILITY_INCONSISTENT),
            )

        history = [*state.tool_history, result.history]
        if not result.history.success:
            moved = advance(state, tool_history=history)
            return GraphUpdate(
                state=moved,
                decision=Decision(safe_stop_reason=SafeStopReason.APPROVAL_REQUEST_FAILED),
            )
        if result.approval is None or not result.response_matches_proposal:
            moved = advance(state, tool_history=history)
            return GraphUpdate(
                state=moved,
                decision=Decision(safe_stop_reason=SafeStopReason.APPROVAL_RESPONSE_INCONSISTENT),
            )

        moved = advance(state, approval=result.approval, tool_history=history)
        return GraphUpdate(state=moved, decision=Decision())

    return {Node.REQUEST_APPROVAL: request_approval}


def build_write_nodes(deps: GraphDeps) -> dict[Node, GraphNode]:
    """Build the money path: ask Java what is allowed, write once, then read authority back.

    These three nodes are the only ones that can lead to money moving, and each of them delegates
    rather than decides: eligibility is Java's judgement, recovery policy is T031's, and the final
    business fact is whatever the authority says afterwards.
    """

    async def check_eligibility(graph: GraphState) -> GraphUpdate:
        """Hand off to Java's deterministic eligibility service with a routing-layer token."""
        state = spend_one_step(graph["state"])
        if state.resolved_order_id is None:
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.EVIDENCE_CONTEXT_MISSING),
            )

        result = await run_eligibility_check(
            eligibility_handoff(graph.get("decision")),
            resolved_order_id=state.resolved_order_id,
            step_index=state.step_count,
            tools=deps.eligibility,
            record_trace=deps.record_trace,
        )
        history = [*state.tool_history, result.history]
        if result.eligibility is None:
            if may_retry_read(result.history, state):
                moved = advance(state, retry_count=state.retry_count + 1, tool_history=history)
                return GraphUpdate(state=moved, decision=Decision(retry_current_stage=True))
            # Java could not answer and we are out of attempts. Finishing here would report "not
            # eligible", which is a claim we cannot make; the run stops instead.
            moved = advance(state, tool_history=history)
            return GraphUpdate(
                state=moved,
                decision=Decision(safe_stop_reason=SafeStopReason.ELIGIBILITY_UNAVAILABLE),
            )

        moved = advance(state, eligibility=result.eligibility, tool_history=history)
        return GraphUpdate(state=moved, decision=Decision())

    async def refund_write(graph: GraphState) -> GraphUpdate:
        """Attempt one logical refund exactly once, and let T031 own every retry decision.

        The node does not retry on any outcome. `RefundWriteOutcome` reports how many attempts T031
        already spent, and a second retry loop here would re-run a policy - read authority first,
        reuse the same key, give up as UNKNOWN - that has exactly one owner.
        """
        state = spend_one_step(graph["state"])
        snapshot = state.eligibility
        if (
            state.resolved_order_id is None
            or snapshot is None
            or snapshot.max_refund_amount is None
        ):
            # The router only sends a bounded, eligible refund here. Reaching this branch means the
            # routing table is incomplete, and refusing beats writing an amount we cannot bound.
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.ELIGIBILITY_AMOUNT_UNBOUNDED),
            )

        intent = refund_write_intent(
            state,
            order_id=state.resolved_order_id,
            reason_code=US1_ELIGIBILITY_REASON_CODE,
            requested_amount=snapshot.max_refund_amount,
            approval_request_id=(
                None
                if (
                    state.approval is None
                    or not state.approval.binding_verified
                    or not snapshot.approval_required
                )
                else state.approval.approval_request_id
            ),
        )

        # The callback T031 calls before its first Tool call. Whatever it returns is the state that
        # now carries a durable intent; if it raises, `persisted` is untouched, and the state this
        # node returns will have no intent - which is exactly true.
        persisted = state

        async def persist(intent_record: WriteIntent, pending: WriteOutcome) -> None:
            nonlocal persisted
            persisted = await deps.persist_intent(persisted, intent_record, pending)

        execution = await execute_refund_write(
            tools=deps.writes,
            intent=intent,
            persist_intent=persist,
            record_trace=deps.record_trace,
            may_already_have_committed=write_may_already_have_committed(state),
            start_step_index=state.step_count,
        )
        outcome = execution.outcome
        moved = advance(
            persisted,
            write=outcome.to_state_outcome(),
            tool_history=[*persisted.tool_history, *execution.history],
        )
        if outcome.error_code == INTENT_NOT_DURABLE_ERROR_CODE:
            # Nothing was sent, and that was the right call: a write whose key might not survive us
            # is the one write we must not attempt. The trace keeps why.
            return GraphUpdate(
                state=moved,
                decision=Decision(safe_stop_reason=SafeStopReason.WRITE_INTENT_NOT_DURABLE),
            )
        return GraphUpdate(state=moved, decision=Decision())

    async def return_write(graph: GraphState) -> GraphUpdate:
        """Attempt one logical return exactly once, and let the executor own every retry decision.

        Mirrors the refund node, with one deliberate difference in what it demands: a *pure* return
        (``RETURN``) carries no amount by contract, so this node must never require one -- the
        amount check stays where money actually moves. What it does require is an eligible snapshot
        whose action authorises a return at all; the router only sends ``RETURN``/``RETURN_REFUND``
        here, so reaching this branch without one means the routing table is incomplete -- and
        refusing beats writing something nobody authorised.
        """
        state = spend_one_step(graph["state"])
        snapshot = state.eligibility
        if (
            state.resolved_order_id is None
            or snapshot is None
            or not snapshot.eligible
            or snapshot.allowed_action not in RETURN_PERMITTING_ACTIONS
        ):
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.ELIGIBILITY_INCONSISTENT),
            )

        intent = return_write_intent(
            state,
            order_id=state.resolved_order_id,
            reason_code=US1_ELIGIBILITY_REASON_CODE,
            approval_request_id=(
                None
                if (
                    state.approval is None
                    or not state.approval.binding_verified
                    or not snapshot.approval_required
                )
                else state.approval.approval_request_id
            ),
        )

        persisted = state

        async def persist(intent_record: WriteIntent, pending: WriteOutcome) -> None:
            nonlocal persisted
            persisted = await deps.persist_intent(persisted, intent_record, pending)

        execution = await execute_return_write(
            tools=deps.writes,
            intent=intent,
            persist_intent=persist,
            record_trace=deps.record_trace,
            may_already_have_committed=write_may_already_have_committed(state),
            start_step_index=state.step_count,
        )
        outcome = execution.outcome
        moved = advance(
            persisted,
            write=outcome.to_state_outcome(),
            tool_history=[*persisted.tool_history, *execution.history],
        )
        if outcome.error_code == INTENT_NOT_DURABLE_ERROR_CODE:
            # Same reading as the refund path: nothing was sent, and that was right.
            return GraphUpdate(
                state=moved,
                decision=Decision(safe_stop_reason=SafeStopReason.WRITE_INTENT_NOT_DURABLE),
            )
        return GraphUpdate(state=moved, decision=Decision())

    async def verify(graph: GraphState) -> GraphUpdate:
        """Read the authoritative after-sales state back, scoped by the same key, and never retry.

        A write response is not the final business fact, and this node is where that belief is
        cashed in: `WriteOutcome` says what we were told, `VerificationOutcome` says what is true.
        """
        state = spend_one_step(graph["state"])
        intent = state.write_intent
        if intent is None or state.resolved_order_id is None:
            # Verification is scoped by the key, so without a durable intent there is no question to
            # ask - and reaching here would mean an incomplete routing table.
            return GraphUpdate(
                state=state,
                decision=Decision(safe_stop_reason=SafeStopReason.WRITE_INTENT_NOT_DURABLE),
            )

        verification = (
            await verify_return_business_state(
                tools=deps.after_sales,
                order_id=state.resolved_order_id,
                idempotency_key=intent.idempotency_key,
                step_index=state.step_count,
                expected_return_request_id=state.write.resource_id,
                record_trace=deps.record_trace,
            )
            if intent.action == CREATE_RETURN_ACTION
            else await verify_refund_business_state(
                tools=deps.after_sales,
                order_id=state.resolved_order_id,
                idempotency_key=intent.idempotency_key,
                step_index=state.step_count,
                expected_refund_request_id=state.write.resource_id,
                record_trace=deps.record_trace,
            )
        )
        moved = advance(state, verification=verification)
        return GraphUpdate(state=moved, decision=Decision())

    return {
        Node.CHECK_ELIGIBILITY: check_eligibility,
        Node.REFUND_WRITE: refund_write,
        Node.RETURN_WRITE: return_write,
        Node.VERIFY: verify,
    }


class SupportTicketTools(Protocol):
    """The single authenticated, state-changing T062 escalation capability."""

    async def create_support_ticket(
        self,
        *,
        run_id: str,
        order_id: str | None,
        category: str,
        reason_code: str,
        evidence_summary: str,
    ) -> ToolEnvelope[TicketResult]:
        ...


def build_lifecycle_nodes(
    tools: SupportTicketTools | None = None, record_trace: TraceSink | None = None
) -> dict[Node, GraphNode]:
    """Build termination nodes and the one authenticated manual-handoff write.

    Finalization stays pure. The optional T062 Tool is only invoked for authoritative
    MANUAL_REVIEW, and its outcome is checkpointed before the lifecycle transition.
    """

    def terminate(state: AgentState, terminal: TerminalDecision) -> GraphUpdate:
        return GraphUpdate(state=state, decision=Decision(terminal=terminal))

    async def finalize(graph: GraphState) -> GraphUpdate:
        """End a run that reached a conclusion, deriving its status from the verified facts."""
        state = graph["state"]
        if state.is_terminal:
            # Already ended. Restating the status would mean inventing the reason it stopped, and
            # the store refuses to move a run out of a terminal state anyway.
            return GraphUpdate(state=state, decision=Decision())
        return terminate(state, terminal_decision_for(state))

    async def safe_stop(graph: GraphState) -> GraphUpdate:
        """End a run that refused to continue, carrying the reason it refused."""
        state = graph["state"]
        reason = safe_stop_reason_for(state, graph.get("decision"))
        if reason is None:
            # A router sent the run here without a reason to give. That is an incomplete routing
            # table, and inventing a reason would hide it - so fail loudly instead.
            raise ValueError("safe_stop was reached without a declared safety reason")
        return terminate(state, TerminalDecision(status=RunStatus.SAFE_STOP, reason=reason))

    async def escalate_or_safe_stop(graph: GraphState) -> GraphUpdate:
        """Call Java exactly once, then checkpoint the result before finalizing.

        LangGraph goes to FINALIZE on the next edge. The runtime checkpoints this
        node's state at that boundary, before setting the terminal run status.
        """
        state = graph["state"]
        snapshot = state.eligibility
        if snapshot is None or snapshot.allowed_action != "MANUAL_REVIEW" or snapshot.eligible:
            raise ValueError("escalate_or_safe_stop requires authoritative MANUAL_REVIEW")
        if tools is None:
            # Unit harnesses with no configured write dependency must not forge a ticket.
            return GraphUpdate(state=state, decision=Decision())
        if state.support_ticket_id is not None:
            # A restored result never triggers another POST.
            return GraphUpdate(state=state, decision=Decision())

        state = spend_one_step(state)

        # No raw LLM messages or arbitrary evidence.data go into the request.
        # Use only the Java eligibility verdict and structured evidence type names.
        evidence_types = sorted(
            {item.evidence_type for item in state.evidence if item.evidence_type.isidentifier()}
        )[:8]
        evidence_facts: list[dict[str, object]] = []
        for item in state.evidence:
            if item.evidence_type != "LOGISTICS" or item.source != "get_logistics":
                continue
            facts = {
                key: value
                for key in ("status", "signed", "stalledHours", "lastMeaningfulEventAt")
                if (value := item.data.get(key)) is not None
                and isinstance(value, str | int | bool)
            }
            evidence_facts.append({"type": "LOGISTICS", "source": "get_logistics", "facts": facts})
            break
        summary = dumps(
            {
                "eligibility": "MANUAL_REVIEW",
                "reasonCode": "MANUAL_REVIEW_REQUIRED",
                "evidenceTypes": evidence_types,
                "evidence": evidence_facts,
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
        if len(summary) > 2000:
            # Never truncate a JSON document into an invalid partial fact.
            summary = dumps(
                {"eligibility": "MANUAL_REVIEW", "reasonCode": "MANUAL_REVIEW_REQUIRED"},
                separators=(",", ":"),
            )
        result = await tools.create_support_ticket(
            run_id=str(state.run_id),
            order_id=state.resolved_order_id,
            category="AFTER_SALES_ESCALATION",
            reason_code="MANUAL_REVIEW_REQUIRED",
            evidence_summary=summary,
        )
        report_tool_call(
            record_trace,
            step_index=state.step_count,
            tool_name="create_support_ticket",
            envelope=result,
            input_summary={
                "runId": str(state.run_id),
                "orderId": state.resolved_order_id,
                "category": "AFTER_SALES_ESCALATION",
                "reasonCode": "MANUAL_REVIEW_REQUIRED",
                "evidenceTypes": evidence_types,
            },
        )
        history = [
            *state.tool_history,
            ToolHistoryEntry(
                step_index=state.step_count,
                tool_name="create_support_ticket",
                success=result.success,
                error_code=result.error_code,
                retryable=False,
                trace_id=result.trace_id,
            ),
        ]
        ticket = result.data
        if not result.success or ticket is None or ticket.status != "OPEN":
            return GraphUpdate(state=advance(state, tool_history=history), decision=Decision())
        return GraphUpdate(
            state=advance(state, tool_history=history, support_ticket_id=ticket.ticket_id),
            decision=Decision(),
        )

    async def waiting_user(graph: GraphState) -> GraphUpdate:
        """End this invocation waiting for the user. The run stays resumable."""
        return terminate(graph["state"], TerminalDecision(status=RunStatus.WAITING_USER))

    async def waiting_approval(graph: GraphState) -> GraphUpdate:
        """End this invocation after Java created a PENDING authoritative approval."""
        state = graph["state"]
        if (
            state.approval is None
            or state.approval.approval_request_id is None
            or state.approval.status != "PENDING"
        ):
            raise ValueError("waiting_approval requires a PENDING authoritative approval reference")
        return terminate(state, TerminalDecision(status=RunStatus.WAITING_APPROVAL))

    return {
        Node.FINALIZE: finalize,
        Node.SAFE_STOP: safe_stop,
        Node.ESCALATE_OR_SAFE_STOP: escalate_or_safe_stop,
        Node.WAITING_USER: waiting_user,
        Node.WAITING_APPROVAL: waiting_approval,
    }
