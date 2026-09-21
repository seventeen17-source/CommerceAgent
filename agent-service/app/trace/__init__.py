"""Agent run, checkpoint and structured tool trace persistence (T017).

What this package is responsible for
------------------------------------
One Agent run has to survive the process that started it. That means three durable facts, not one:

* the **run row** (``agent.agent_runs``) -- the queryable projection: what status, whose run, which
  order, how far it got, and the compare-and-swap ``version`` that makes concurrent writes safe;
* the **checkpoints** (``agent.agent_checkpoints``) -- what the runtime state *was* at each step, so
  a run can be resumed and a failed run can be reconstructed;
* the **tool trace** (``agent.tool_executions``) -- ``run_id + step_index + trace_id`` plus the
  error/retry/outcome summary, so a failure can be followed back to one specific Java request.

The three are written through :class:`~app.trace.store.PostgresRunStore`. Read
``app/trace/store.py`` for the concurrency argument (row lock *plus* version compare-and-swap), and
``app/trace/retention.py`` for why terminal-run cleanup keeps failed runs longer than completed
ones.

Security
--------
Nothing in this package trusts its input. Every payload is passed through
:func:`app.security.secrets.validate_persistable` immediately before it is bound into SQL, so a raw
token or hidden reasoning cannot reach a checkpoint or a trace even when it bypassed model
validation -- which is exactly what happens when a checkpoint is restored from a raw dict.
"""

from __future__ import annotations

__all__: list[str] = []
