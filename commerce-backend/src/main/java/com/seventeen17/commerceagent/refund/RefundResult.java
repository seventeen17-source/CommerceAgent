package com.seventeen17.commerceagent.refund;

import java.math.BigDecimal;

/**
 * T021：退款写入的结果（对应契约 {@code RefundResult}）。
 *
 * <p>三个字段都是**权威事实**：`refundRequestId` 来自数据库里真实存在的行，`status` 是该行的当前状态，
 * `acceptedAmount` 是服务端实际接受的金额。Agent 不得把"我请求了 X"当成"系统接受了 X"——写后验证（T031）读的
 * 就是这个对象背后的行。
 *
 * <p>{@code acceptedAmount} 在 V1 恒等于订单全额：本版本只做整单退款，服务端**不会**静默把请求金额改成别的数。
 */
public record RefundResult(String refundRequestId, RefundStatus status, BigDecimal acceptedAmount) {

    static RefundResult from(RefundRequest refund) {
        return new RefundResult(refund.getId(), refund.getStatus(), refund.getAmount());
    }
}
