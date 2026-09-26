package com.seventeen17.commerceagent.refund;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * T028 HTTP boundary for money-moving refunds and their authoritative verification read.
 *
 * <p>The controller stays intentionally thin. It never trusts request text, requested amount or
 * run id as authorization evidence; {@link RefundService} owns every business check immediately
 * before commit. The optional recovery filter is scoped by the service to authenticated user +
 * order + idempotency key, so an unrelated refund on the same order cannot be mistaken for the
 * timed-out logical write.
 */
@RestController
@RequestMapping("/api/v1")
public class RefundController {

    private final RefundService refundService;

    public RefundController(RefundService refundService) {
        this.refundService = refundService;
    }

    @PostMapping("/refunds")
    RefundResult createRefund(
            @AuthenticationPrincipal CommercePrincipal principal,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody CreateRefundRequest request) {
        return refundService.createRefund(principal, idempotencyKey, request.toCommand());
    }

    @GetMapping("/orders/{orderId}/after-sales")
    AfterSalesStatusResponse getAfterSalesStatus(
            @AuthenticationPrincipal CommercePrincipal principal,
            @PathVariable String orderId,
            @RequestParam(required = false) String idempotencyKey) {
        List<RefundResult> refunds = idempotencyKey == null
                ? refundService.listRefunds(principal, orderId)
                : refundService.listRefunds(principal, orderId, idempotencyKey);
        return AfterSalesStatusResponse.refundsOnly(refunds);
    }
}
