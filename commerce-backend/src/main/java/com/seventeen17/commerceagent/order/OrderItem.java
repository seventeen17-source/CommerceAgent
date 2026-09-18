package com.seventeen17.commerceagent.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

/**
 * `commerce.order_items` —— 订单明细。
 *
 * <p>注意两点：
 *
 * <ul>
 *   <li>该表**没有** `version` 列，因此不做乐观锁：明细是订单聚合内的一部分，其一致性由订单聚合根的一个事务保证，
 *       不需要各自独立的版本号。
 *   <li>`unit_price` 是权威持久化价格。退款资格与金额计算必须读这里，不能用模型输出或检索文本推算
 *       （data-model 明确要求）。
 * </ul>
 */
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    /**
     * 所属订单。`updatable = false`：明细不能在订单之间搬家，否则退款归属会出现无法解释的漂移。
     */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false, updatable = false)
    private Order order;

    @Column(name = "product_id", length = 64, nullable = false)
    private String productId;

    @Column(name = "product_name", length = 255, nullable = false)
    private String productName;

    /** 决定适用哪条售后规则的类目；V001 上有索引。 */
    @Column(name = "product_category", length = 100, nullable = false)
    private String productCategory;

    @Column(name = "unit_price", precision = 19, scale = 2, nullable = false)
    private BigDecimal unitPrice;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    /** JPA 要求的无参构造器；业务代码请用下面的工厂方法。 */
    protected OrderItem() {}

    public static OrderItem create(
            String id,
            String productId,
            String productName,
            String productCategory,
            BigDecimal unitPrice,
            int quantity) {
        OrderItem item = new OrderItem();
        item.id = id;
        item.productId = productId;
        item.productName = productName;
        item.productCategory = productCategory;
        item.unitPrice = unitPrice;
        item.quantity = quantity;
        return item;
    }

    /** 只能由 {@link Order#addItem} / {@link Order#removeItem} 调用，保证双向关系一致。 */
    void assignTo(Order order) {
        this.order = order;
    }

    public String getId() {
        return id;
    }

    /**
     * 只返回订单 id，**不返回** {@code Order} 引用。
     *
     * <p>否则调用方可以 {@code item.getOrder().setStatus(...)}，绕过聚合根 {@link Order} 直接改订单状态。
     * SpotBugs 的 EI_EXPOSE_REP 告警指的正是这件事 —— 与其压制告警，不如把聚合边界画干净。
     */
    public String getOrderId() {
        return order == null ? null : order.getId();
    }

    public String getProductId() {
        return productId;
    }

    public String getProductName() {
        return productName;
    }

    public String getProductCategory() {
        return productCategory;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }
}
