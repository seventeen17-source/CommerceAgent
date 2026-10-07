package com.seventeen17.commerceagent.order;

/**
 * 订单售后状态（Java 侧枚举）。
 *
 * <p><b>重要：这不是数据库完整性约束。</b> `commerce.orders.after_sales_status` 列在 V001 中**没有** CHECK
 * 约束，数据库仍会接受任意字符串。本枚举只约束经由 Java 代码的写入。
 *
 * <p>列为可空：`null` 表示"该订单尚无任何售后动作"，因此这里不定义 `NONE` 之类的占位值 —— 让"没有售后"在数据上
 * 就是 `null`，而不是一个需要被记住的特殊取值。
 *
 * <p>取值集合为 V1 最小集（对应 US1 退款与 US2 退货两条路径），完整售后状态机由 T026 定义后扩展。
 */
public enum AfterSalesStatus {
    /** 已发起退款申请。 */
    REFUND_REQUESTED,
    /** 已发起退货申请。 */
    RETURN_REQUESTED
}
