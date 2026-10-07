"""Dev/test-only HTTP harness for observing the T029 Agent Tool boundary.

This router exists for the Flow Playground. It is not a business API and it intentionally excludes
high-risk write capabilities. Every request still authenticates normally, then executes through
ToolRegistry -> CommerceTools -> CommerceClient -> Java.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.clients.commerce_client import CommerceClient
from app.security.dependencies import AppSettings, AuthenticatedCall, authenticate
from app.tools import CommerceTools, ToolEnvelope, ToolRegistry

__all__ = ["router"]

router = APIRouter(
    prefix="/agent/dev/tools",
    tags=["dev-tools"],
    dependencies=[Depends(authenticate)],
)

AuthenticatedDep = Annotated[AuthenticatedCall, Depends(authenticate)]


class _DebugRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListOrdersRequest(_DebugRequest):
    tool_name: Literal["list_user_orders"] = Field(alias="toolName")


class GetOrderRequest(_DebugRequest):
    tool_name: Literal["get_order"] = Field(alias="toolName")
    order_id: str = Field(alias="orderId", min_length=1, max_length=64)


class GetLogisticsRequest(_DebugRequest):
    tool_name: Literal["get_logistics"] = Field(alias="toolName")
    order_id: str = Field(alias="orderId", min_length=1, max_length=64)


class CheckEligibilityRequest(_DebugRequest):
    tool_name: Literal["check_after_sales_eligibility"] = Field(alias="toolName")
    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    reason_code: str = Field(alias="reasonCode", min_length=1, max_length=100)


class GetAfterSalesStatusRequest(_DebugRequest):
    tool_name: Literal["get_after_sales_status"] = Field(alias="toolName")
    order_id: str = Field(alias="orderId", min_length=1, max_length=64)
    idempotency_key: str | None = Field(
        default=None, alias="idempotencyKey", min_length=8, max_length=128
    )


SafeDebugToolRequest = Annotated[
    ListOrdersRequest
    | GetOrderRequest
    | GetLogisticsRequest
    | CheckEligibilityRequest
    | GetAfterSalesStatusRequest,
    Field(discriminator="tool_name"),
]


def _client(request: Request) -> CommerceClient:
    client = getattr(request.app.state, "commerce_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COMMERCE_CLIENT_UNAVAILABLE",
        )
    return cast(CommerceClient, client)


@router.post("/execute")
async def execute_safe_tool(
    body: SafeDebugToolRequest,
    request: Request,
    call: AuthenticatedDep,
    settings: AppSettings,
) -> ToolEnvelope[Any]:
    """Execute one safe T029 capability for the local Flow Playground."""
    if settings.environment not in {"dev", "test"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

    tools = CommerceTools(client=_client(request), auth=call.auth)
    implementation = ToolRegistry(tools=tools).resolve(body.tool_name)

    if isinstance(body, ListOrdersRequest):
        return await implementation()
    if isinstance(body, GetOrderRequest):
        return await implementation(body.order_id)
    if isinstance(body, GetLogisticsRequest):
        return await implementation(body.order_id)
    if isinstance(body, CheckEligibilityRequest):
        return await implementation(body.order_id, body.reason_code)
    if isinstance(body, GetAfterSalesStatusRequest):
        return await implementation(body.order_id, idempotency_key=body.idempotency_key)

    raise AssertionError("unreachable safe tool request variant")
