package com.seventeen17.commerceagent.refund;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

/**
 * T028 HTTP request body for {@code POST /api/v1/refunds}.
 *
 * <p>Identity and idempotency are deliberately absent from the JSON body: ownership comes only
 * from the authenticated {@code CommercePrincipal}, while the logical write identity comes from
 * the {@code Idempotency-Key} header. The descriptive reason and requested amount remain
 * untrusted inputs; {@link RefundService} revalidates eligibility and the authoritative amount
 * immediately before commit.
 */
public record CreateRefundRequest(
        @NotBlank @Size(max = 64) String orderId,
        @NotBlank @Size(max = 100) String reasonCode,
        @Positive BigDecimal requestedAmount,
        @Size(max = 64) String approvalRequestId,
        @NotBlank @Size(max = 64) String runId) {

    RefundCommand toCommand() {
        return new RefundCommand(orderId, reasonCode, requestedAmount, approvalRequestId, runId);
    }
}
