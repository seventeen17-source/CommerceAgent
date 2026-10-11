"""Decide-evidence dump for one Agent run: why it stopped, and what it left behind.

Usage (from ``agent-service``)::

    .\\.venv\\Scripts\\python.exe probe_us5_run.py              # latest ESCALATED / SAFE_STOP run
    .\\.venv\\Scripts\\python.exe probe_us5_run.py <run-id>     # one specific run

Why this exists next to the eval runner rather than inside it: the runner *grades* a case and prints
pass/fail, which is the right output for a gate. When a gate fails -- or when someone asks "why did
this run stop?" -- what is needed is the raw decision trail: the terminal checkpoint's reason code,
the Tool trace, and the authority rows the run produced. Both halves matter and neither is a
substitute for the other: a verdict without evidence is unarguable, and a dump without a verdict
never fails.

Reads authority storage directly (``commerce.*`` with the business role, ``agent.*`` with the agent
role), so nothing here can be answered by the Agent's own story.

Note on the filename: this was produced during the T063 live-gate session and could not be renamed
from inside the sandbox that created it (sub-directory renames are denied there). It belongs at
``agent-service/scripts/run_evidence.py``; the file name does not change what it does.
"""

from __future__ import annotations

import argparse

import psycopg

from app.config.settings import Settings

COMMERCE_DSN = "postgresql://commerce_app:commerce_app_dev_only@127.0.0.1:5432/commerceagent"


def agent_kwargs() -> dict[str, object]:
    """Connection kwargs for the Agent-owned tables, with the local-host IPv4 fix.

    The Docker database publishes IPv4 only, while ``localhost`` resolves to ``::1`` first on this
    host, so every connection would otherwise wait out its timeout before falling back.
    """
    settings = Settings()
    host = "127.0.0.1" if settings.postgres_host == "localhost" else settings.postgres_host
    return {
        "host": host,
        "port": settings.postgres_port,
        "dbname": settings.postgres_db,
        "user": settings.agent_app_user,
        "password": settings.agent_app_password,
        "connect_timeout": 5,
    }


def resolve_run_id(cursor: psycopg.Cursor, requested: str | None) -> str | None:
    if requested:
        return requested
    cursor.execute("""
        SELECT run_id FROM agent.agent_runs
         WHERE status IN ('ESCALATED', 'SAFE_STOP')
         ORDER BY started_at DESC LIMIT 1
        """)
    row = cursor.fetchone()
    return None if row is None else str(row[0])


def dump_trace(cursor: psycopg.Cursor, run_id: str) -> str | None:
    """Print the Agent-owned half, and return the order the run resolved.

    The order comes back from here rather than being joined in the business query below: the two
    halves are read under *different roles* (the point of the schema split), so a cross-schema join
    would be a permission error dressed up as evidence.
    """
    cursor.execute(
        "SELECT run_id, status, step_count, retry_count, current_node, error_code, "
        "resolved_order_id FROM agent.agent_runs WHERE run_id = %s",
        (run_id,),
    )
    row = cursor.fetchone()
    print("run (run_id, status, steps, retries, node, error_code, order):", row)
    order_id = None if row is None else row[6]

    cursor.execute(
        "SELECT version, status, reason_code FROM agent.agent_checkpoints "
        "WHERE run_id = %s ORDER BY version DESC LIMIT 1",
        (run_id,),
    )
    print("terminal checkpoint (version, status, reason_code):", cursor.fetchone())

    cursor.execute(
        "SELECT step_index, tool_name, status, error_code, risk_level "
        "FROM agent.tool_executions WHERE run_id = %s ORDER BY step_index, id",
        (run_id,),
    )
    print("tool trace:")
    for entry in cursor.fetchall():
        print("   ", entry)
    return order_id


def dump_authority(run_id: str, order_id: str | None) -> None:
    with (
        psycopg.connect(COMMERCE_DSN, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT id, user_id, order_id, category, reason_code, status, evidence_summary "
            "FROM commerce.support_tickets WHERE run_id = %s",
            (run_id,),
        )
        tickets = cursor.fetchall()
        print(f"support_tickets rows for this run: {len(tickets)}")
        for ticket in tickets:
            print("    ticket:", ticket[:6])
            print("    evidence_summary:", ticket[6])

        cursor.execute(
            "SELECT action, resource_type, resource_id, result, metadata_json "
            "FROM commerce.audit_logs WHERE run_id = %s AND action = 'SUPPORT_TICKET_CREATED'",
            (run_id,),
        )
        print("SUPPORT_TICKET_CREATED audits:", cursor.fetchall())

        if order_id is None:
            print("run resolved no order, so there is nothing to count writes against")
            return
        cursor.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM commerce.refund_requests WHERE order_id = %s), "
            "(SELECT COUNT(*) FROM commerce.return_requests WHERE order_id = %s)",
            (order_id, order_id),
        )
        print(f"after-sales writes on {order_id} (refunds, returns):", cursor.fetchone())


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump one Agent run's decision evidence.")
    parser.add_argument("run_id", nargs="?", default=None)
    args = parser.parse_args()

    with psycopg.connect(**agent_kwargs()) as connection, connection.cursor() as cursor:
        run_id = resolve_run_id(cursor, args.run_id)
        if run_id is None:
            print("no ESCALATED/SAFE_STOP run found; pass a run id explicitly")
            return
        order_id = dump_trace(cursor, run_id)
    dump_authority(run_id, order_id)


if __name__ == "__main__":
    main()
