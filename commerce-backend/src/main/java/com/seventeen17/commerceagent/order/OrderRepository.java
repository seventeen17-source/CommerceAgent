package com.seventeen17.commerceagent.order;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 订单仓储。
 *
 * <p>这里的方法刻意都带 ownership 维度：调用方必须先确定"当前认证用户是谁"，而不是传入任意 userId。查询本身不构成
 * 授权，但把 ownership 放进方法签名能让"忘了校验归属"这件事更难发生（真正的鉴权在 T011）。
 */
public interface OrderRepository extends JpaRepository<Order, String> {

    List<Order> findByOwnerIdOrderByCreatedAtDesc(String ownerId);

    Optional<Order> findByIdAndOwnerId(String id, String ownerId);

    boolean existsByIdAndOwnerId(String id, String ownerId);
}
