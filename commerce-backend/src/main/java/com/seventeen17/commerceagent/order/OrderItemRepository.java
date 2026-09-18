package com.seventeen17.commerceagent.order;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

/** 订单明细仓储。按订单查询即可满足 V1 需求。 */
public interface OrderItemRepository extends JpaRepository<OrderItem, String> {

    List<OrderItem> findByOrder_Id(String orderId);
}
