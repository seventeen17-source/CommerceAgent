package com.seventeen17.commerceagent.returns;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * T040 HTTP request body for {@code POST /api/v1/returns}（对应契约 {@code CreateReturnRequest}）。
 *
 * <p>Identity and idempotency are deliberately absent from the JSON body, exactly as for refunds:
 * ownership comes only from the authenticated principal, while the logical write identity comes from
 * the {@code Idempotency-Key} header. {@code reasonCode} and {@code returnMethod} remain untrusted,
 * descriptive inputs; {@link ReturnService} revalidates eligibility immediately before commit.
 */
public record CreateReturnRequest(
        @NotBlank @Size(max = 64) String orderId,
        @NotBlank @Size(max = 100) String reasonCode,
        @Size(max = 32) String returnMethod,
        @Size(max = 64) String approvalRequestId,
        @NotBlank @Size(max = 64) String runId) {

    ReturnCommand toCommand() {
        return new ReturnCommand(orderId, reasonCode, returnMethod, approvalRequestId, runId);
    }
}
