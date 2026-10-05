package com.seventeen17.commerceagent.returns;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * {@code commerce.return_requests} 的读面，刻意与 {@code RefundRequestRepository} 对称。
 *
 * <p>这三个派生查询不是随手加的，它们各自对应一种"必须按 owner 收窄"的读：
 *
 * <ul>
 *   <li>{@link #findByUserIdAndIdempotencyKey} —— 幂等重放的读回。按 <b>user</b> 而不是全表查 key：
 *       幂等键的命名空间属于用户，全表查会让别人的 key 影响你的结果，也会让"这个 key 用过没"变成一条
 *       跨用户的泄露。
 *   <li>{@link #findByOrderIdAndUserIdOrderByCreatedAtAsc} —— 一个订单的退货时间线，按 owner 收窄，
 *       别人的订单读出来一定是空列表。
 *   <li>{@link #findByOrderIdAndUserIdAndIdempotencyKey} —— "这一笔<b>是不是我这次逻辑写</b>产生的"。
 *       它防的是把同一订单上<b>别人</b>（或另一次尝试）产生的退货误认成自己的成功 —— T031 的写后恢复
 *       就是靠这个精度，而不是靠"这个订单上有没有行"。
 * </ul>
 *
 * <p>没有写方法：写入由服务层在事务里完成，仓库不承担规则判断。
 */
public interface ReturnRequestRepository extends JpaRepository<ReturnRequest, String> {

    Optional<ReturnRequest> findByUserIdAndIdempotencyKey(String userId, String idempotencyKey);

    List<ReturnRequest> findByOrderIdAndUserIdOrderByCreatedAtAsc(String orderId, String userId);

    Optional<ReturnRequest> findByOrderIdAndUserIdAndIdempotencyKey(
            String orderId, String userId, String idempotencyKey);
}
