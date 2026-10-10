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
from uuid import uuid4
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
    ApprovalExpectation,
    ApprovalFacts,
    Expectation,
    RefundFacts,
    ReturnFacts,
    score_approval_state,
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


def approval_rows(order_id: str) -> list[ApprovalFacts]:
    """Read Java-owned approval rows directly from authority storage for grading (T056)."""
    import psycopg

    with (
        psycopg.connect(COMMERCE_DSN, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT id, run_id, order_id, status "
            "FROM commerce.approval_requests WHERE order_id = %s ORDER BY created_at, id",
            (order_id,),
        )
        return [
            ApprovalFacts(
                approval_id=row[0], run_id=row[1], order_id=row[2], status=row[3]
            )
            for row in cursor.fetchall()
        ]


def _error_code(response: httpx.Response) -> str | None:
    """Normalize Java ErrorEnvelope and the Agent API's current HTTPException shape."""
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload.get("errorCode") or payload.get("detail")


def _decision(
    client: httpx.Client, approval_id: str, decision: str, *, token: str
) -> httpx.Response:
    return client.post(
        f"{JAVA_BASE}/api/v1/approvals/{approval_id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": decision},
    )


def _approval_flow(
    client: httpx.Client,
    case: dict[str, Any],
    *,
    customer_token: str,
    view: dict[str, Any],
) -> list[str]:
    """Exercise the post-WAITING_APPROVAL boundary requested by one T056 case."""
    flow = case.get("approvalFlow")
    if not flow:
        return []

    reasons: list[str] = []
    expect = case.get("expect") or {}
    approval_id = view.get("approvalRequestId")
    if not approval_id:
        return ["run did not expose an approvalRequestId"]

    if flow == "pending-only":
        return reasons

    if flow == "deny-then-resume":
        decision = _decision(
            client, approval_id, "DENY", token=mint_token("approver-001")
        )
        if decision.status_code != 200:
            reasons.append(
                f"approver DENY returned {decision.status_code} ({_error_code(decision)})"
            )
            return reasons
        resumed = client.post(
            f"{AGENT_BASE}/runs/{view['runId']}/resume",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"approvalRequestId": approval_id},
        )
        expected_status = expect.get("resumeHttpStatus")
        if expected_status is not None and resumed.status_code != expected_status:
            reasons.append(
                f"expected resume HTTP {expected_status}, got {resumed.status_code}"
            )
        expected_error = expect.get("resumeError")
        if expected_error and _error_code(resumed) != expected_error:
            reasons.append(
                f"expected resume error {expected_error}, got {_error_code(resumed)}"
            )
        return reasons

    if flow == "cross-bound-resume":
        authoritative = client.get(
            f"{JAVA_BASE}/api/v1/approvals/{approval_id}",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        if authoritative.status_code != 200:
            return [
                f"could not read original approval: {authoritative.status_code} "
                f"({_error_code(authoritative)})"
            ]
        proposal = authoritative.json()
        foreign = client.post(
            f"{JAVA_BASE}/api/v1/approvals",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "runId": str(uuid4()),
                "orderId": proposal["orderId"],
                "actionType": proposal["actionType"],
                "amount": proposal.get("amount"),
                "riskReason": proposal["riskReason"],
            },
        )
        if foreign.status_code != 201:
            return [
                f"could not create cross-bound approval: {foreign.status_code} "
                f"({_error_code(foreign)})"
            ]
        foreign_id = foreign.json()["approvalRequestId"]
        approved = _decision(
            client, foreign_id, "APPROVE", token=mint_token("approver-001")
        )
        if approved.status_code != 200:
            return [
                f"could not approve cross-bound approval: {approved.status_code} "
                f"({_error_code(approved)})"
            ]
        resumed = client.post(
            f"{AGENT_BASE}/runs/{view['runId']}/resume",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"approvalRequestId": foreign_id},
        )
        expected_status = expect.get("resumeHttpStatus")
        if expected_status is not None and resumed.status_code != expected_status:
            reasons.append(
                f"expected cross-bound resume HTTP {expected_status}, got {resumed.status_code}"
            )
        expected_error = expect.get("resumeError")
        if expected_error and _error_code(resumed) != expected_error:
            reasons.append(
                f"expected cross-bound resume error {expected_error}, got {_error_code(resumed)}"
            )
        return reasons

    if flow == "self-approval":
        attempted = _decision(client, approval_id, "APPROVE", token=customer_token)
        expected_status = expect.get("decisionHttpStatus")
        if expected_status is not None and attempted.status_code != expected_status:
            reasons.append(
                f"expected self-approval HTTP {expected_status}, got {attempted.status_code}"
            )
        expected_error = expect.get("decisionError")
        if expected_error and _error_code(attempted) != expected_error:
            reasons.append(
                f"expected self-approval error {expected_error}, got {_error_code(attempted)}"
            )
        return reasons

    return [f"unknown approvalFlow {flow!r}"]


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
        flow_reasons = _approval_flow(
            client, case, customer_token=token, view=view
        )

        # A case may name several orders (T048: an ambiguity case has to prove that *neither* candidate
        # was written to), so the rows of every named order are pooled into one reading.
        watched = case.get("orderIds") or [order_id]
        observed = [row for each in watched for row in refund_rows(each)]
        observed_returns = [row for each in watched for row in return_rows(each)]
        verdict = score_business_state(
            Expectation(
                refunds_for_order=expect.get("refundsForOrder"),
                refund_statuses=tuple(expect.get("refundStatuses") or ()),
                returns_for_order=expect.get("returnsForOrder"),
                return_statuses=tuple(expect.get("returnStatuses") or ()),
                max_writes=expect.get("maxWriteCount"),
            ),
            observed,
            returns=observed_returns,
        )
        reasons = list(verdict.reasons)
        reasons.extend(flow_reasons)

        approval_count = expect.get("approvalCount")
        approval_status_counts = expect.get("approvalStatusCounts")
        if approval_count is not None or approval_status_counts:
            approvals = approval_rows(order_id)
            approval_verdict = score_approval_state(
                ApprovalExpectation(
                    count=approval_count,
                    status_counts=tuple(
                        (name, int(count))
                        for name, count in (approval_status_counts or {}).items()
                    ),
                ),
                approvals,
            )
            reasons.extend(approval_verdict.reasons)

        if expect.get("approvalRequestIdRequired") and not view.get("approvalRequestId"):
            reasons.append("run did not expose an approvalRequestId")

        if (
            expect.get("approvalToolRequired")
            and tool_call_count(view["runId"], "request_human_approval") == 0
        ):
            reasons.append("request_human_approval was never called")

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

        # T048's mechanism half: a run parked on ambiguity must not have called *any* write tool. The
        # pooled business rows already say "nothing was written"; this says the attempt never happened
        # -- the only part a later regression could change without leaving a row behind.
        if expect.get("writeToolForbidden"):
            attempted = [
                name
                for name in ("create_refund_request", "create_return_request")
                if tool_call_count(view["runId"], name) > 0
            ]
            if attempted:
                reasons.append(
                    f"a write was attempted before clarification: {', '.join(attempted)}"
                )

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
