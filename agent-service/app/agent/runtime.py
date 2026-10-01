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

from app.agent.graph import CompiledGraph, GraphState
from app.agent.routing import Decision, Node, TerminalDecision
from app.agent.state import AgentState, WriteIntent, WriteOutcome, advance
from app.trace.checkpoint import RunRecord, Transition
from app.trace.errors import RunStoreError
from app.trace.store import RunStore

__all__ = ["RunSession", "drive_graph"]


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
        """The callback T031 invokes before its first Tool call.

        It advances the payload and checkpoints it in the same breath, because the entire point of
        the seam is that the key is durable *before* the request is. Raising here is the designed
        failure: T031 then sends nothing at all.
        """
        moved = advance(state, write_intent=intent, write=outcome)
        return self.checkpoint(state=moved, current_node=Node.REFUND_WRITE.value)

    def finish(self, terminal: TerminalDecision, *, current_node: str) -> None:
        """Write the lifecycle change that ends this invocation.

        The counters and the payload are deliberately not repeated here: the last boundary
        checkpoint already wrote them, and ``transition`` updates only what it is given.
        ``final_action`` names the protected action the run actually attempted - ``None`` means it
        never reached one, which is a fact rather than a blank.
        """
        state = self.state
        self._record = self._store.transition(
            self._record.run_id,
            Transition(
                expected_version=self._record.version,
                status=terminal.status,
                trigger="TERMINAL",
                current_node=current_node,
                final_action=state.write_intent.action if state.write_intent is not None else None,
                reason_code=terminal.reason.value if terminal.reason is not None else None,
            ),
        )


async def drive_graph(graph: CompiledGraph, session: RunSession) -> RunRecord:
    """Run one invocation, persisting at every node boundary, and return the final record.

    The boundary write is deferred by exactly one step, and that is on purpose: only once the *next*
    node starts do we know where the run actually went, so the previous boundary is written with a
    real ``next_action`` instead of a guess. The routers stay the only thing that decides where a
    run goes - there is no second copy of that decision here to drift away from theirs.

    An exception propagates untouched and the run stays ``RUNNING``. Deciding how a crashed run gets
    marked is a policy question for the caller, not a mechanism for this function to guess at.
    """

    if session.record.is_terminal:
        # Driving a run that already ended would walk a graph whose first router sends it straight
        # to finalize, and finalize reports no decision - so refuse here, where the reason is clear.
        raise RunStoreError("this run is already terminal; there is nothing to drive")

    pending: tuple[AgentState, str] | None = None
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
                previous_state, previous_node = pending
                session.checkpoint(
                    state=previous_state,
                    current_node=previous_node,
                    next_action=node_name,
                )

            if decision is not None and decision.terminal is not None:
                # The run ends here. The boundary checkpoint above already holds this node's
                # payload, and a lifecycle change must go through transition() rather than a
                # checkpoint.
                session.finish(decision.terminal, current_node=node_name)
                return session.record

            pending = (state, node_name)

    raise RunStoreError(
        "the graph stopped without a terminal decision; the routing table is incomplete"
    )
