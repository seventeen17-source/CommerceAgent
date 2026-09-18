package com.seventeen17.commerceagent.logistics;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.io.Serializable;

/**
 * 仅用于给 `shipments.order_id` 这个外键提供实体引用，而不把整个 {@code order} 包拖进物流包。
 *
 * <p>做法说明：JPA 的关联目标必须是实体。如果直接把 {@code Order} 作为关联类型，`logistics` 包就会依赖
 * `order` 包（并且写订单时要加载订单实体）。这里用一个只映射主键的轻量实体指向同一张表，等价于"我只关心这个
 * 外键的值"。Hibernate 支持同一张表被多个实体映射，只要写入路径不冲突。
 */
@Entity
@Table(name = "orders")
public class OrderRef implements Serializable {

    @Id
    @jakarta.persistence.Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    protected OrderRef() {}

    OrderRef(String id) {
        this.id = id;
    }

    public String getId() {
        return id;
    }
}
