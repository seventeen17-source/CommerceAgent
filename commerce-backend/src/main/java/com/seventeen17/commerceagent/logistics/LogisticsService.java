package com.seventeen17.commerceagent.logistics;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T019：客户维度的物流读能力。
 *
 * <p>两个容易写错的点：
 *
 * <ul>
 *   <li><b>先过 ownership，再读物流。</b>物流轨迹本身就是敏感数据。如果因为"这只是读物流"就省掉归属校验，
 *       {@code orderId} 立刻变成越权读别人物流的入口。这里复用 {@link OrderService#requireOwnedOrder} 而不是
 *       自己再写一遍判断，是为了让"越权长什么样"只有一处定义。
 *   <li><b>没有运单不能一律当成 503。</b>如果订单仍是 {@link OrderStatus#PAID}，"没有运单"是正常的业务状态，
 *       此时返回 {@link ErrorCode#INVALID_ORDER_STATE}（non-retryable），避免 Agent 把"尚未发货"误当成依赖故障反复
 *       重试；如果订单已经进入发货/履约阶段却没有权威运单记录，则返回
 *       {@link ErrorCode#LOGISTICS_UNAVAILABLE}（retryable），并继续禁止 Agent 猜测物流事实。
 * </ul>
 *
 * <p>注意 ownership 校验与运单读取是两次独立查询，中间没有锁。这在本项目是安全的：{@code orders.user_id} 在映射
 * 层被声明为 {@code updatable = false}（T009），订单归属创建后不可变，所以两次查询之间不存在"归属被改掉"的窗口。
 */
@Service
@Transactional(readOnly = true)
public class LogisticsService {

    private final OrderService orderService;
    private final ShipmentRepository shipmentRepository;
    private final LogisticsEventRepository logisticsEventRepository;
    private final LogisticsStallCalculator stallCalculator;

    public LogisticsService(
            OrderService orderService,
            ShipmentRepository shipmentRepository,
            LogisticsEventRepository logisticsEventRepository,
            LogisticsStallCalculator stallCalculator) {
        this.orderService = orderService;
        this.shipmentRepository = shipmentRepository;
        this.logisticsEventRepository = logisticsEventRepository;
        this.stallCalculator = stallCalculator;
    }

    public LogisticsSnapshot getLogistics(CommercePrincipal principal, String orderId) {
        Order order = orderService.requireOwnedOrder(principal, orderId);

        Shipment shipment = shipmentRepository.findByOrderId(orderId).orElseThrow(() -> missingShipment(order));

        // 方法名里的 `Shipment_Id` 让 Spring Data 直接走 shipment_id 外键列，
        // 不会为了取一个时间戳而把 Shipment 实体再加载一次（LogisticsEvent.shipment 是 LAZY）。
        Optional<Instant> latestEventAt = logisticsEventRepository
                .findFirstByShipment_IdOrderByOccurredAtDesc(shipment.getId())
                .map(LogisticsEvent::getOccurredAt);

        return stallCalculator.assess(shipment, latestEventAt.orElse(null));
    }

    private static BusinessException missingShipment(Order order) {
        if (order.getStatus() == OrderStatus.PAID) {
            return new BusinessException(
                    ErrorCode.INVALID_ORDER_STATE, "Order has not been shipped; logistics are not applicable yet");
        }
        return new BusinessException(
                ErrorCode.LOGISTICS_UNAVAILABLE, "No authoritative logistics record exists for this order");
    }
}
