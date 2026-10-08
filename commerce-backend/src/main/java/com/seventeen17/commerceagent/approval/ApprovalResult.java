package com.seventeen17.commerceagent.approval;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * HTTP projection of one authoritative approval row.
 *
 * <p>The binding fields are intentionally returned together with status. A consumer that reads only
 * {@code status=APPROVED} and ignores run/order/action/amount has thrown away the authorization.
 */
public record ApprovalResult(
        String approvalRequestId,
        String runId,
        String orderId,
        String actionType,
        BigDecimal amount,
        String riskReason,
        ApprovalStatus status,
        String decidedBy,
        Instant decidedAt) {

    static ApprovalResult from(ApprovalRequest request) {
        return new ApprovalResult(
                request.getId(),
                request.getRunId(),
                request.getOrderId(),
                request.getAction().name(),
                request.getAmount(),
                request.getReasonCode(),
                request.getStatus(),
                request.getDecidedBy(),
                request.getDecidedAt());
    }
}
