"""Run the US1 eval cases: reset the world, run the agent, grade the business state.

Usage (from the repository root)::

    python eval/runner.py --dataset eval/datasets/dev/us1_logistics_refund.yaml

What it refuses to do
---------------------
If the reset endpoint is not reachable, this exits with an **infrastructure failure**, not a model
failure. The eval contract says so explicitly, and the reason is arithmetic: a run that could not
start from a known world tells you nothing about the agent, and counting it as a wrong answer quietly
poisons the success rate. The reset route is registered only under the test/eval profile, so a dev
profile backend correctly produces this outcome rather than a silent pass.

Why the recovery read is asserted separately
--------------------------------------------
See the dataset's header. A case that only counts rows passes when the agent did nothing at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

# The eval tree and the agent service are deliberately separate: the runner drives the agent from
# outside, so it must not become importable as part of it. Two paths are added explicitly rather than
# relying on the working directory, because `python script.py` puts the *script's* directory on
# sys.path rather than the current one:
#   * eval/          so `scorers.*` resolves
#   * agent-service/ only to reuse the configured JWT issuer/secret when minting eval tokens
_EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_EVAL_DIR))
sys.path.insert(0, str(_EVAL_DIR.parent / "agent-service"))

from scorers.business_state import (
    Expectation,
    RefundFacts,
    ReturnFacts,
    score_business_state,
)

AGENT_BASE = "http://127.0.0.1:8000/api/v1/agent"
JAVA_BASE = "http://127.0.0.1:8080"
#: The agent's own role cannot read the business schema (by design), so the facts are read with the
#: business role. That separation is exactly what stops the agent from grading itself.
COMMERCE_DSN = (
    "postgresql://commerce_app:commerce_app_dev_only@127.0.0.1:5432/commerceagent"
)


@dataclass(frozen=True)
class Outcome:
    case_id: str
    kind: str  # "pass" | "fail" | "infrastructure"
    detail: str


def load_cases(path: Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(document["cases"])


def mint_token(user_id: str) -> str:
    from datetime import UTC, datetime, timedelta

    import jwt
    from app.config.settings import Settings  # type: ignore[import-not-found]

    settings = Settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.commerce_jwt_issuer,
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        settings.commerce_jwt_secret,
        algorithm="HS256",
    )


def reset_case(client: httpx.Client, case: dict[str, Any]) -> str | None:
    """Return an infrastructure failure message, or None when the world is ready."""
    try:
        response = client.post(
            f"{JAVA_BASE}/internal/eval/fixtures/{case['caseId']}/reset",
            # Every route is behind `anyRequest().authenticated()`, reset included, so an
            # unauthenticated reset is refused with 401 rather than 404 -- which is also why a 401
            # says nothing about whether the endpoint is registered. Only the profile does.
            headers={"Authorization": f"Bearer {mint_token(case['user'])}"},
        )
    except httpx.HTTPError as exc:
        return f"reset endpoint unreachable: {type(exc).__name__}"
    if response.status_code == 401:
        return "reset refused with 401 - the runner must authenticate this call"
    if response.status_code == 404:
        return (
            "reset endpoint is not registered - it exists only under the test/eval profile, "
            "so this backend cannot provide a deterministic starting world"
        )
    if response.status_code >= 500:
        return f"reset failed with {response.status_code} (EVAL_RESET_FAILED)"
    if response.status_code >= 400:
        return f"reset refused with {response.status_code}"
    return None


def refund_rows(order_id: str) -> list[RefundFacts]:
    import psycopg

    with (
        psycopg.connect(COMMERCE_DSN, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT order_id, status FROM commerce.refund_requests WHERE order_id = %s",
            (order_id,),
        )
        return [
            RefundFacts(order_id=row[0], status=row[1]) for row in cursor.fetchall()
        ]


def return_rows(order_id: str) -> list[ReturnFacts]:
    """Fetch this order's return rows (T042), under the same shape rule as refunds.

    Read from the authority's own storage with the *business* role, never through the Agent's API:
    the Agent must not be able to grade itself.
    """
    import psycopg

    with (
        psycopg.connect(COMMERCE_DSN, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT order_id, status FROM commerce.return_requests WHERE order_id = %s",
            (order_id,),
        )
        return [
            ReturnFacts(order_id=row[0], status=row[1]) for row in cursor.fetchall()
        ]


def tool_call_count(run_id: str, tool_name: str) -> int:
    """How many times this run recorded one Tool name in the cross-service evidence table.

    This is the mechanism half of a T042 assertion. Business rows say what the world looks like; they
    cannot say *whose path* produced it, and a prohibition ("no refund row") cannot be told apart from
    a run that never got out of bed. The Tool trace can.
    """
    import psycopg
    from app.config.settings import Settings  # type: ignore[import-not-found]

    with (
        psycopg.connect(Settings().agent_database_url, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT count(*) FROM agent.tool_executions WHERE run_id = %s AND tool_name = %s",
            (run_id, tool_name),
        )
        return int((cursor.fetchone() or [0])[0])


def recovery_read_happened(run_id: str) -> bool:
    """True only when a *lost* write was recovered: an unknown outcome, then an authority read.

    The plain verify read is not enough. Every successful run reads authority after writing, so
    accepting any such read would let this case pass with no timeout and no unknown write at all --
    a false pass of exactly the kind this assertion exists to prevent. The sequence is what makes it
    evidence: the write first reported that it did not know, and only then did the run go and ask.
    """
    import psycopg
    from app.config.settings import Settings  # type: ignore[import-not-found]

    with (
        psycopg.connect(Settings().agent_database_url, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT step_index, error_code FROM agent.tool_executions "
            "WHERE run_id = %s AND tool_name = %s ORDER BY step_index",
            (run_id, "create_refund_request"),
        )
        unknown_steps = [
            row[0] for row in cursor.fetchall() if row[1] == "WRITE_TIMEOUT_UNKNOWN"
        ]
        if not unknown_steps:
            return False
        cursor.execute(
            "SELECT count(*) FROM agent.tool_executions "
            "WHERE run_id = %s AND tool_name = %s AND step_index > %s",
            (run_id, "get_after_sales_status", min(unknown_steps)),
        )
        return (cursor.fetchone() or [0])[0] > 0


def run_case(case: dict[str, Any], order_id: str) -> Outcome:
    # T042: a case may name its own order. The eval world is no longer a single order -- a delivered
    # case and a shipped case cannot share one -- and the alternative (one CLI flag for the whole
    # dataset) would make the dataset unrunnable as soon as it holds two worlds.
    order_id = case.get("orderId") or order_id
    expect = case.get("expect") or {}
    with httpx.Client(timeout=300.0, trust_env=False) as client:
        problem = reset_case(client, case)
        if problem is not None:
            return Outcome(
                case.get("scenarioId") or case["caseId"], "infrastructure", problem
            )

        token = mint_token(case["user"])
        # A case can ask more than once. "The same request twice" is the entire point of the
        # duplicate case, and asking once would let it pass without testing anything: a single
        # request produces one row whether or not idempotency works at all. Each request is its own
        # run, which is what a customer pressing send twice actually does.
        views: list[dict[str, Any]] = []
        for _ in range(int(case.get("repeatRequest") or 1)):
            response = client.post(
                f"{AGENT_BASE}/runs",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": case["request"]},
            )
            if response.status_code != 201:
                return Outcome(
                    case.get("scenarioId") or case["caseId"],
                    "fail",
                    f"run was not created: {response.status_code}",
                )
            views.append(response.json())
        view = views[-1]

        observed = refund_rows(order_id)
        observed_returns = return_rows(order_id)
        verdict = score_business_state(
            Expectation(
                refunds_for_order=expect.get("refundsForOrder"),
                refund_statuses=tuple(expect.get("refundStatuses") or ()),
                returns_for_order=expect.get("returnsForOrder"),
                return_statuses=tuple(expect.get("returnStatuses") or ()),
            ),
            observed,
            returns=observed_returns,
        )
        reasons = list(verdict.reasons)

        if (
            expect.get("terminalStatus")
            and view.get("status") != expect["terminalStatus"]
        ):
            reasons.append(
                f"expected status {expect['terminalStatus']}, got {view.get('status')}"
            )

        # The mechanism half of the assertion: without it, "wrote nothing" would pass a case whose
        # whole point is that a lost write was recovered.
        if expect.get("recoveryReadRequired") and not recovery_read_happened(
            view["runId"]
        ):
            reasons.append("no recovery read (get_after_sales_status) was performed")

        # T042's mechanism half. `refundToolForbidden` is the executable form of "a delivered order is
        # never granted a direct refund": the rows already forbid the *result*, and this forbids the
        # *attempt* -- the part that would otherwise be invisible, since a refused attempt leaves no
        # business row at all.
        if (
            expect.get("returnToolRequired")
            and tool_call_count(view["runId"], "create_return_request") == 0
        ):
            reasons.append(
                "the return write never happened (create_return_request was not called)"
            )
        if (
            expect.get("refundToolForbidden")
            and tool_call_count(view["runId"], "create_refund_request") > 0
        ):
            reasons.append("a refund write was attempted for a delivered order")

    kind = "pass" if not reasons else "fail"
    return Outcome(
        case.get("scenarioId") or case["caseId"],
        kind,
        "; ".join(reasons) or "business state matches the case",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the US1 eval dataset.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument(
        "--order-id", default="order-001", help="the order the case writes against"
    )
    args = parser.parse_args(argv)

    outcomes = [run_case(case, args.order_id) for case in load_cases(args.dataset)]
    for outcome in outcomes:
        print(f"[{outcome.kind:>14}] {outcome.case_id}: {outcome.detail}")
    print(
        json.dumps(
            {o.kind: sum(1 for x in outcomes if x.kind == o.kind) for o in outcomes}
        )
    )

    # Infrastructure failures are returned as their own exit code so a caller can never mistake them
    # for a poor model score.
    return 2 if any(o.kind == "infrastructure" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
