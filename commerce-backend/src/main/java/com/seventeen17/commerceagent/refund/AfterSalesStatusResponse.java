package com.seventeen17.commerceagent.refund;

import com.seventeen17.commerceagent.returns.ReturnResult;
import java.util.List;

/**
 * T028/T040 authoritative read model used by post-write verification and unknown-write recovery.
 *
 * <p>Both arrays are always present. An explicit empty list means the authority checked the requested scope
 * and found nothing committed; an omitted field would not carry that safety meaning. T040 adds the returns
 * half: a return write is verified by reading this same aggregate back, so both object kinds arrive together
 * and a caller cannot "verify" a return by looking at a view that never shows returns.
 *
 * <p><b>Known tradeoff</b>: the refund module now knows about the returns module. V1 has exactly two
 * after-sales objects and the contract defines their read model as one aggregate ({@code AfterSalesStatus}),
 * so extracting an aggregator would be a third file owning one line of logic. When a third object kind
 * appears (support tickets, approvals), that is the moment to extract it — the same judgement T019 recorded
 * for reusing the service read-side instead of rewriting it per endpoint.
 */
public record AfterSalesStatusResponse(List<RefundResult> refunds, List<ReturnResult> returns) {

    public AfterSalesStatusResponse {
        refunds = List.copyOf(refunds);
        returns = List.copyOf(returns);
    }

    static AfterSalesStatusResponse of(List<RefundResult> refunds, List<ReturnResult> returns) {
        return new AfterSalesStatusResponse(refunds, returns);
    }
}
