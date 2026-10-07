package com.seventeen17.commerceagent.order;

/** `commerce.orders.status` 的取值，与数据库 CHECK 约束一一对应。 */
public enum OrderStatus {
    PAID,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    CLOSED
}
