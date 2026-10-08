package com.seventeen17.commerceagent.approval;

import com.seventeen17.commerceagent.eligibility.AllowedAction;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.UUID;

/**
 * HTTP body for creating a human approval request.
 *
 * <p>Every field is still untrusted input. {@link ApprovalService} re-runs deterministic
 * eligibility and requires action/amount/risk reason to match the authoritative decision before
 * anything is persisted. In particular, this object can ask for an approval; it cannot create an
 * APPROVED status.
 */
public record CreateApprovalRequest(
        @NotNull UUID runId,
        @NotBlank @Size(max = 64) String orderId,
        @NotNull AllowedAction actionType,
        @Positive BigDecimal amount,
        @NotBlank
                @Size(max = 100)
                @Pattern(regexp = "^[A-Z0-9_:-]+$")
                String riskReason) {}
