package com.seventeen17.commerceagent.refund;

import java.util.List;

/**
 * T028 authoritative read model used by post-write verification and unknown-write recovery.
 *
 * <p>Both arrays are always present. An explicit empty {@code refunds} list means the authority
 * checked the requested scope and found no committed refund; an omitted field would not carry that
 * safety meaning. Returns are not implemented until US2, so V1 reports an explicit empty array.
 */
public record AfterSalesStatusResponse(List<RefundResult> refunds, List<Object> returns) {

    public AfterSalesStatusResponse {
        refunds = List.copyOf(refunds);
        returns = List.copyOf(returns);
    }

    static AfterSalesStatusResponse refundsOnly(List<RefundResult> refunds) {
        return new AfterSalesStatusResponse(refunds, List.of());
    }
}
