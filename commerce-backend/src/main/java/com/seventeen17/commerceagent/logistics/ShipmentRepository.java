package com.seventeen17.commerceagent.logistics;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 物流主记录仓储。
 *
 * <p>由于 V1 是“一个订单最多一个包裹”，按订单查询返回 {@code Optional} 而不是列表 —— 让关系基数在方法签名上就
 * 表达出来。
 */
public interface ShipmentRepository extends JpaRepository<Shipment, String> {

    Optional<Shipment> findByOrderId(String orderId);

    boolean existsByOrderId(String orderId);
}
