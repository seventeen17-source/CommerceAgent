package com.seventeen17.commerceagent.returns;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * T040 HTTP boundary for {@code POST /api/v1/returns}.
 *
 * <p>Deliberately thin, exactly like {@code RefundController}: request text is never authorization
 * evidence, and {@link ReturnService} owns every business check immediately before commit. Identity comes
 * only from the authenticated principal; the logical write identity comes only from the
 * {@code Idempotency-Key} header.
 *
 * <p>The authoritative after-sales <b>read</b> stays on {@code GET /orders/{orderId}/after-sales} (owned by
 * {@code RefundController} since T028) because the contract defines it as one aggregate of every
 * after-sales object, refunds and returns together.
 */
@RestController
@RequestMapping("/api/v1")
public class ReturnController {

    private final ReturnService returnService;

    public ReturnController(ReturnService returnService) {
        this.returnService = returnService;
    }

    @PostMapping("/returns")
    ReturnResult createReturn(
            @AuthenticationPrincipal CommercePrincipal principal,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody CreateReturnRequest request) {
        return returnService.createReturn(principal, idempotencyKey, request.toCommand());
    }
}
