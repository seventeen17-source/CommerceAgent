package com.seventeen17.commerceagent.returns;

/**
 * {@code commerce.return_requests.status} 的取值，与 V004 的 {@code chk_return_requests_status} 一一对应。
 *
 * <p>它不是数据库完整性约束的替代品：CHECK 约束才是最终把关，枚举只约束经 Java 的写入。V1 只产生
 * {@link #CREATED}；退货的收货与结算属于后续任务。
 *
 * <p>{@link #REJECTED} 与 {@link #CANCELLED} 被 V004 的部分唯一索引排除在"活动"之外 —— 只有这两个终态才
 * 允许同一订单再开一笔新的退货。
 */
public enum ReturnStatus {
    /** 已创建，等待后续处理。V1 的终态。 */
    CREATED,
    PROCESSING,
    COMPLETED,
    /** 被拒绝：不再占用该订单的"活动退货"名额。 */
    REJECTED,
    /** 被取消：同上。 */
    CANCELLED
}
