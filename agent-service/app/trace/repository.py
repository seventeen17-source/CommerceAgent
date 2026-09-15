from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run_id: str
    user_id: str
    status: str
    current_node: str | None
    step_count: int
    payload: dict[str, Any]


class AgentRunRepository:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def create(self, run_id: str, user_id: str, payload: dict[str, Any]) -> None:
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                """
                INSERT INTO agent.agent_runs
                    (run_id, user_id, status, current_node, step_count, retry_count, state_json, started_at)
                VALUES (%s, %s, 'RUNNING', 'created', 0, 0, %s::jsonb, %s)
                """,
                (run_id, user_id, json.dumps(payload), datetime.now(UTC)),
            )

    def get_for_owner(self, run_id: str, user_id: str) -> AgentRunRecord | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT run_id, user_id, status, current_node, step_count, state_json
                FROM agent.agent_runs
                WHERE run_id = %s AND user_id = %s
                """,
                (run_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return AgentRunRecord(
            run_id=row["run_id"],
            user_id=row["user_id"],
            status=row["status"],
            current_node=row["current_node"],
            step_count=row["step_count"],
            payload=row["state_json"] or {},
        )

    def append_event(
        self,
        run_id: str,
        step_index: int,
        event_type: str,
        summary: str,
        *,
        status: str = "SUCCESS",
        error_code: str | None = None,
    ) -> None:
        with psycopg.connect(self._dsn) as conn:
            conn.execute(
                """
                INSERT INTO agent.tool_executions
                    (run_id, step_index, tool_name, risk_level, input_summary, output_summary,
                     status, error_code, retryable, latency_ms, trace_id, created_at)
                VALUES (%s, %s, %s, 'SYSTEM', NULL, %s, %s, %s, false, 0, NULL, %s)
                """,
                (run_id, step_index, event_type, summary, status, error_code, datetime.now(UTC)),
            )
