package com.seventeen17.commerceagent.order;

import java.math.BigDecimal;
import java.util.List;

/**
 * 订单详情读模型（对应契约 {@code OrderSnapshot}）。
 *
 * <p>它是 {@code @Transactional(readOnly = true)} 事务**内部**组装出来的 detached 值对象：事务一结束 Hibernate
 * 的 session 就关了，只有已经拷进读模型的普通字段还可用。这就是"Service 必须返回 snapshot 而不是实体"的真正
 * 原因，不是代码风格偏好。
 *
 * <p>字段集刻意与契约保持一致：明细**不带** {@code unit_price}。退款上限这类金额计算由服务端（T025 的确定性
 * 资格服务）用权威持久化价格完成，不把逐行价格交给消费端自行拼算。
 *
 * <p>{@code afterSalesStatus} 可以为 {@code null}：`null` 表示"该订单尚无任何售后动作"，与枚举里放一个
 * {@code NONE} 占位值是两件事（见 {@link AfterSalesStatus} 的说明）。
 */
public record OrderSnapshot(
        String orderId,
        OrderStatus status,
        BigDecimal totalAmount,
        String currency,
        AfterSalesStatus afterSalesStatus,
        List<Item> items) {

    /**
     * 紧凑构造器里做防御性拷贝：record 的访问器会把内部引用直接交出去，若存入调用方传来的可变列表，外部后续
     * 修改就会"从后面"改变一个已经读出的快照。
     */
    public OrderSnapshot {
        items = List.copyOf(items);
    }

    /** 明细行，只暴露契约声明的字段。 */
    public record Item(String productId, String productName, String productCategory, int quantity) {}
}
