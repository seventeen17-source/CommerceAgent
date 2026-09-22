package com.seventeen17.commerceagent.logistics;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Component;

/**
 * T019：物流派生事实的**唯一**计算处。
 *
 * <p>把"签收判定"和"停滞时长"放在同一个类里不是偷懒，而是因为它们被同一条规则绑在一起：<b>已签收 ⇒ 停滞不
 * 适用</b>。若两者分居两处，改了一处忘了另一处，就会出现"已签收订单却带着 120 小时停滞"这种自相矛盾的证据包，
 * 而 US2 明确要求已签收订单必须走退货，不能继续走未签收退款。
 *
 * <p>三个刻意的计算口径（每一个都决定了钱会不会被错误地退出去）：
 *
 * <ol>
 *   <li><b>基准取"最近一次确实有过的动静"</b>：
 *       {@code max(shipments.last_event_at, MAX(logistics_events.occurred_at))}。{@code last_event_at} 是投影列，
 *       它与事件表之间**没有任何数据库约束防止漂移**。取较大值等于取"最近的活动"，方向上是**低估**停滞时长 ——
 *       而低估只会让我们少退款，不会多退款。
 *   <li><b>没有物流事实就不编造</b>：两个来源都为空时返回 {@code null}，**不回落**到 {@code orders.shipped_at}。
 *       "物流停滞"的基准必须是物流事实；拿订单的发货时间冒充物流事件，会让证据看起来比实际更充分，而这正是
 *       US5 要禁止的"凭推测继续"。
 *   <li><b>向下取整</b>：47 小时 59 分算 47 小时。阈值比较是 {@code stalledHours >= threshold}，向下取整让判定
 *       偏向"未达阈值"，同样是 fail closed 方向。若向上取整，47.1 小时就能蒙混过 48 小时的门槛。
 * </ol>
 */
@Component
public class LogisticsStallCalculator {

    private final Clock clock;

    public LogisticsStallCalculator(Clock clock) {
        this.clock = clock;
    }

    /**
     * 把权威物流数据折算成读模型。
     *
     * @param latestEventOccurredAt 事件表里最近一条事件的 {@code occurred_at}；没有任何事件时为 {@code null}
     */
    public LogisticsSnapshot assess(Shipment shipment, Instant latestEventOccurredAt) {
        boolean signed = isSigned(shipment);
        Instant baseline = latestOf(shipment.getLastEventAt(), latestEventOccurredAt);
        if (baseline == null || signed) {
            // 已签收时 stalledHours 保持 null：签收意味着物流已经走完，"停滞"不再是一个有意义的量。
            return new LogisticsSnapshot(shipment.getStatus(), signed, baseline, null);
        }
        long stalledHours = Duration.between(baseline, clock.instant()).toHours();
        // 时间戳落在未来（时钟偏移或脏数据）时夹到 0：不谎报停滞，但也不销毁事实——
        // lastMeaningfulEventAt 照实暴露那个未来时间戳，异常本身仍然看得见。
        return new LogisticsSnapshot(shipment.getStatus(), signed, baseline, Math.max(0L, stalledHours));
    }

    /**
     * 是否已签收。
     *
     * <p>两个来源任一成立即按已签收处理：{@code signed_at} 是签收事实的时间戳，{@code status = DELIVERED} 是运单
     * 自己的状态。两者冲突时（例如状态已 DELIVERED 但签收时间没落库）刻意选择**按已签收处理**，因为方向不对称：
     * 误判为未签收会打开本不该走的退款路径（资金风险），误判为已签收只会让 Agent 走退货或人工路径（可纠正）。
     */
    public static boolean isSigned(Shipment shipment) {
        return shipment.getSignedAt() != null || shipment.getStatus() == ShipmentStatus.DELIVERED;
    }

    private static Instant latestOf(Instant first, Instant second) {
        if (first == null) {
            return second;
        }
        if (second == null) {
            return first;
        }
        return first.isAfter(second) ? first : second;
    }
}
