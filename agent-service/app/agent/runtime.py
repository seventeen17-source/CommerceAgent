"""The durable seam between one graph invocation and the run row (T032 Step 5).

Nodes never write durable state. This module is the only place that does, and it does it at **node
boundaries** rather than inside business logic. Two writes exist and they are not interchangeable:

* ``checkpoint_state`` persists the payload at the same status - the facts
  (``write_intent`` / ``write`` / ``verification``) that are not row projections;
* ``transition`` performs a lifecycle change, with the guard that keeps a run from moving anywhere
  it should not.

Both are bound to the version the previous write produced, and tracking that version is this
module's job: the store refuses a write computed from a version that is no longer current, which is
precisely what stops two executors from overwriting each other's work.
"""

from __future__ import annotations

import logging
from typing import Final

from app.agent.execute_write import CREATE_REFUND_ACTION, CREATE_RETURN_ACTION
from app.agent.graph import CompiledGraph, GraphState
from app.agent.routing import Decision, Node, TerminalDecision
from app.agent.state import AgentState, RunStatus, WriteIntent, WriteOutcome, advance
from app.agent.tool_tracing import ToolCallFacts, build_trace_record
from app.tools.models import ToolRisk
from app.trace.checkpoint import RunRecord, Transition
from app.trace.errors import RunStoreError, RunVersionConflictError, TerminalRunError
from app.trace.store import RunStore

__all__ = ["FAILED_RUN_ERROR_CODE", "RunSession", "drive_graph"]

logger = logging.getLogger(__name__)

#: What a run is marked with when the invocation itself failed. It is the same code T031 uses for an
#: intent that could not be persisted, because both say the same thing: our side broke, so the run's
#: outcome is unknown rather than negative - and neither may be reported as a business answer.
FAILED_RUN_ERROR_CODE = "INTERNAL_ERROR"

#: Which write node owns each durable action name. Derived from the intent rather than passed in by
#: the caller: the intent *is* the durable fact about which logical write this is, so the checkpoint
#: cannot disagree with it -- and a return write can never be recorded on ``refund_write``.
_WRITE_NODE_FOR_ACTION: Final[dict[str, str]] = {
    CREATE_REFUND_ACTION: Node.REFUND_WRITE.value,
    CREATE_RETURN_ACTION: Node.RETURN_WRITE.value,
}


def write_node_for(intent: WriteIntent) -> str:
    """The node name a write intent belongs to, failing closed on an unknown action.

    Raising here is deliberate and not expensive: the executor treats a raise from the persist
    callback as "the key could not be made durable", so an unrecognised action sends nothing at all.
    """
    try:
        return _WRITE_NODE_FOR_ACTION[intent.action]
    except KeyError as exc:
        raise ValueError(f"unknown write action: {intent.action}") from exc


class RunSession:
    """One invocation's view of a run: its state, its version, and the two write seams.

    Every successful write replaces :attr:`record`, so the version handed to the next write is
    always the one the store just produced. A session is not safe to share between two executors,
    and it does not need to be: whoever loses the race gets ``RunVersionConflictError`` instead of a
    lost update.
    """

    def __init__(self, store: RunStore, record: RunRecord) -> None:
        self._store = store
        self._record = record

    @property
    def record(self) -> RunRecord:
        return self._record

    @property
    def state(self) -> AgentState:
        """The authoritative state: the payload with the row's shared columns applied.

        Read through the record rather than straight off the payload so that the row - which is what
        a CAS write just succeeded against - is the fresher fact whenever the two disagree.
        """
        state = self._record.to_state()
        if state is None:
            raise RunStoreError("this run's payload has been reclaimed; there is nothing to drive")
        return state

    def checkpoint(
        self,
        *,
        state: AgentState,
        current_node: str,
        next_action: str | None = None,
    ) -> AgentState:
        """Persist the payload as it stands at a node boundary, and return the row-applied state."""
        # A write-ahead intent can be persisted while the graph is still running a node.
        # Never let a delayed node-boundary checkpoint roll back that durable fact or its budget.
        current = self.state
        if state.step_count < current.step_count:
            raise RunStoreError("checkpoint would decrease the durable step count")
        if current.write_intent is not None and state.write_intent != current.write_intent:
            raise RunStoreError("checkpoint would discard or replace a durable write intent")
        self._record = self._store.checkpoint_state(
            self._record.run_id,
            expected_version=self._record.version,
            state=state,
            current_node=current_node,
            next_action=next_action,
        )
        return self.state

    async def persist_intent(
        self,
        state: AgentState,
        intent: WriteIntent,
        outcome: WriteOutcome,
    ) -> AgentState:
        """The callback the write executor invokes before its first Tool call.

        It advances the payload and checkpoints it in the same breath, because the entire point of
        the seam is that the key is durable *before* the request is. Raising here is the designed
        failure: the executor then sends nothing at all.
        """
        moved = advance(state, write_intent=intent, write=outcome)
        return self.checkpoint(state=moved, current_node=write_node_for(intent))

    def record_trace(self, facts: ToolCallFacts, risk: ToolRisk | None) -> None:
        """Write one Tool call to the cross-service evidence table.

        Here rather than at the call site because two of the three inputs are this session's: the
        run id, and the store. Risk arrives as a parameter because the registry owns it - a call
        site that had to classify its own call would be guessing at something it never sees.
        """
        self._store.record_tool_trace(
            build_trace_record(run_id=self._record.run_id, facts=facts, risk=risk)
        )

    def finish(
        self,
        terminal: TerminalDecision,
        *,
        current_node: str,
        error_code: str | None = None,
    ) -> None:
        """Write the lifecycle change that ends this invocation.

        The counters and the payload are deliberately not repeated here: the last boundary
        checkpoint already wrote them, and ``transition`` updates only what it is given.
        ``final_action`` names the protected action the run actually attempted - ``None`` means it
        never reached one, which is a fact rather than a blank. The payload is read defensively
        because this same method records a failed invocation, and a failed invocation is exactly the
        case where retention may already have reclaimed it.
        """
        payload = self._record.to_state()
        attempted: str | None = None
        if payload is not None and payload.write_intent is not None:
            attempted = payload.write_intent.action
        self._record = self._store.transition(
            self._record.run_id,
            Transition(
                expected_version=self._record.version,
                status=terminal.status,
                trigger="TERMINAL",
                current_node=current_node,
                final_action=attempted,
                error_code=error_code,
                reason_code=terminal.reason.value if terminal.reason is not None else None,
            ),
        )


def _mark_failed(session: RunSession) -> None:
    """Record that this invocation failed, without replacing the error that caused it.

    Two refusals are expected and quiet, because in both cases writing FAILED would mean a stale
    executor overwriting a live run: a version conflict says someone else advanced this run, and a
    terminal run says someone else already finished it. Anything else - including the store being
    unreachable, which is often the very thing that raised - is logged, because then the run is left
    ``RUNNING`` with no executor at all, and an operator has to be able to find it. ``RUNNING`` is
    deliberately not resumable, so such a run would otherwise be indistinguishable from live work.
    """
    try:
        session.finish(
            TerminalDecision(status=RunStatus.FAILED),
            current_node=session.record.current_node or "unknown",
            error_code=FAILED_RUN_ERROR_CODE,
        )
    except (RunVersionConflictError, TerminalRunError):
        return
    except RunStoreError:
        logger.warning("could not mark run %s as failed", session.record.run_id, exc_info=True)


async def drive_graph(graph: CompiledGraph, session: RunSession) -> RunRecord:
    """Run one invocation, persisting at every node boundary, and return the final record.

    The boundary write is deferred by exactly one step, and that is on purpose: only once the *next*
    node starts do we know where the run actually went, so the previous boundary is written with a
    real ``next_action`` instead of a guess. The routers stay the only thing that decides where a
    run goes - there is no second copy of that decision here to drift away from theirs.

    Every way out of this function that is not a terminal transition marks the run ``FAILED`` first,
    then re-raises. The re-raise matters as much as the marking: the failure is recorded *in
    addition to* being surfaced, never instead of it, so a bug in this codebase cannot be filed away
    as just another failed run. Leaving the run ``RUNNING`` instead is not an option - that status
    belongs to a live executor, and nothing would ever collect it.
    """
    if session.record.is_terminal:
        # A precondition, not an invocation failure: the run is not ours to drive, so nothing is
        # written and the caller learns why.
        raise RunStoreError("this run is already terminal; there is nothing to drive")

    try:
        # Carry the store version that produced each delayed boundary. A write node may
        # durably checkpoint its idempotency intent before yielding its GraphUpdate.
        pending: tuple[AgentState, str, int] | None = None
        invocation: GraphState = {
            "state": session.state,
            "decision": Decision(),
            "understood": None,
            "resolution": None,
        }

        async for chunk in graph.astream(invocation, stream_mode="updates"):
            for raw_name, update in chunk.items():
                node_name = str(raw_name)
                state: AgentState = update["state"]
                decision: Decision | None = update.get("decision")

                if pending is not None:
                    previous_state, previous_node, previous_version = pending
                    if session.record.version == previous_version:
                        session.checkpoint(
                            state=previous_state,
                            current_node=previous_node,
                            next_action=node_name,
                        )
                    # If the store version advanced while this node ran, its write-ahead
                    # intent is already durable. Flushing the older pending state would
                    # erase the key and roll the budget backwards (observed at T054 v15/v16).

                if decision is not None and decision.terminal is not None:
                    # The run ends here. The boundary checkpoint above already holds this node's
                    # payload, and a lifecycle change must go through transition(), not a
                    # checkpoint.
                    session.finish(decision.terminal, current_node=node_name)
                    return session.record

                pending = (state, node_name, session.record.version)

        raise RunStoreError(
            "the graph stopped without a terminal decision; the routing table is incomplete"
        )
    except Exception:
        _mark_failed(session)
        raise
