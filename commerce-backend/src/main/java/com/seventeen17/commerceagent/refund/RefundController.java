package com.seventeen17.commerceagent.refund;

import com.seventeen17.commerceagent.returns.ReturnResult;
import com.seventeen17.commerceagent.returns.ReturnService;
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
 * T028/T040 HTTP boundary for money-moving refunds, return writes and their authoritative verification read.
 *
 * <p>The controller stays intentionally thin. It never trusts request text, requested amount or
 * run id as authorization evidence; {@link RefundService} owns every business check immediately
 * before commit. The optional recovery filter is scoped by the service to authenticated user +
 * order + idempotency key, so an unrelated refund on the same order cannot be mistaken for the
 * timed-out logical write.
 *
 * <p>T040 extends only the <b>read</b> side here: the contract defines
 * {@code GET /orders/{orderId}/after-sales} as one aggregate of every after-sales object, so the returns
 * half is read through {@link ReturnService} and returned in the same response. The return <b>write</b>
 * lives in {@code ReturnController}.
 */
@RestController
@RequestMapping("/api/v1")
public class RefundController {

    private final RefundService refundService;
    private final ReturnService returnService;

    public RefundController(RefundService refundService, ReturnService returnService) {
        this.refundService = refundService;
        this.returnService = returnService;
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
        // 退货那一半也必须按同一个 key 过滤：写后验证问的是"我这一笔到底落没落库"，而不是"这个订单上有过什么"。
        List<ReturnResult> returns = idempotencyKey == null
                ? returnService.listReturns(principal, orderId)
                : returnService.listReturns(principal, orderId, idempotencyKey);
        return AfterSalesStatusResponse.of(refunds, returns);
    }
}
