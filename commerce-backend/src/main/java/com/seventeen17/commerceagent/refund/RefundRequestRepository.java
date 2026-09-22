package com.seventeen17.commerceagent.refund;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 退款仓储。
 *
 * <p>与 {@code OrderRepository} 同一条约定：每个查询都带 ownership 维度。这里没有"按 id 查退款"的便利方法，因为
 * 调用方真正需要的是"我的某笔退款"或"我这个订单下的退款"；{@code JpaRepository} 自带的 {@code findById} 仍然存在
 * （见 T019 的教训：仓储方法名是约定，不是强制），因此真正的把关必须在服务层。
 */
public interface RefundRequestRepository extends JpaRepository<RefundRequest, String> {

    /**
     * 幂等键查找。<b>必须</b>带 {@code userId}：key 的命名空间属于用户，没有这条谓词就会出现"拿别人的 key 读回
     * 别人的退款"。
     */
    Optional<RefundRequest> findByUserIdAndIdempotencyKey(String userId, String idempotencyKey);

    /** 某订单下的退款列表（写后验证与超时恢复的读面）。同样带 owner 谓词做纵深防御。 */
    List<RefundRequest> findByOrderIdAndUserIdOrderByCreatedAtAsc(String orderId, String userId);
}
