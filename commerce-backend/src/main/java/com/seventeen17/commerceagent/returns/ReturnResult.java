package com.seventeen17.commerceagent.returns;

import java.time.Instant;

/**
 * T040：退货写入的结果（对应契约 {@code ReturnResult}）。
 *
 * <p>三个字段都是**权威事实**：{@code returnRequestId} 来自数据库里真实存在的行，{@code status} 是该行的当前
 * 状态，{@code returnDeadline} 是**受理时冻结**的截止时刻（不是读的时候再算一遍的）。Agent 的写后验证
 * （T031 的口径）读的就是这个对象背后的行，而不是相信"我请求过"。
 *
 * <p>{@code returnDeadline} 可以为 {@code null}：契约如此声明，且将来一条不带窗口的退货规则会合法地产生
 * {@code null}。V1 的决策只在窗口可算时放行退货，所以 V1 写出来的行一定带值。
 */
public record ReturnResult(String returnRequestId, ReturnStatus status, Instant returnDeadline) {

    static ReturnResult from(ReturnRequest request) {
        return new ReturnResult(request.getId(), request.getStatus(), request.getReturnDeadline());
    }
}
