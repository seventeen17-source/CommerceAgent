package com.seventeen17.commerceagent.order;

import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

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

    /**
     * T021：写路径专用的行锁读（{@code SELECT ... FOR UPDATE}）。
     *
     * <p><b>ownership 写在锁查询自己的 WHERE 里</b>，而不是"先锁住任意订单再检查归属"：锁只应当加在调用方有权看见的
     * 行上，否则一条越权请求也能让别人的订单行被阻塞。归属不匹配时这里返回空，由服务层套用与读路径完全相同的
     * concealment 语义。
     *
     * <p>它与 {@code findByIdAndOwnerId} 的差别只有锁，<b>但锁的价值完全取决于外层事务</b>：没有事务的
     * {@code FOR UPDATE} 会在语句结束时就释放，等于没锁，还会让人误以为已经串行化了。因此调用方必须处在写事务里，
     * 见 {@code OrderService#requireOwnedOrderForUpdate}。
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id and o.ownerId = :ownerId")
    Optional<Order> findByIdAndOwnerIdForUpdate(@Param("id") String id, @Param("ownerId") String ownerId);
}
