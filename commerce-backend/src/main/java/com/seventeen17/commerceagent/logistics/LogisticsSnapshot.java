package com.seventeen17.commerceagent.logistics;

import java.time.Instant;

/**
 * 物流读模型（对应契约 {@code LogisticsSnapshot}）。
 *
 * <p>两个可空字段不是"还没实现"，而是**语义的一部分**：
 *
 * <ul>
 *   <li>{@code lastMeaningfulEventAt == null} 表示"没有任何可用的权威物流事件"；
 *   <li>{@code stalledHours == null} 表示"停滞时长无法判定"。
 * </ul>
 *
 * <p>它们与"停滞 0 小时"是**完全不同的两件事**：前者是"不知道"，后者是"刚刚才有过动静"。把它们合并成 0，会让
 * "证据不足"看起来像"证据充分且未达阈值"，于是 Agent 会自信地得出错误结论——而 US5 明确要求证据不足时转人工，
 * 不是靠推理补上缺失的证据。
 */
public record LogisticsSnapshot(
        ShipmentStatus status, boolean signed, Instant lastMeaningfulEventAt, Long stalledHours) {

    /**
     * 是否达到给定停滞阈值。
     *
     * <p>证据缺失（{@code stalledHours == null}）时返回 {@code false}。这样调用方（T025 的确定性资格判定）用
     * {@code snapshot.stalledAtLeast(rule.logisticsStalledHours())} 这种自然写法时，"不知道"必然落到
     * "不足以判定为停滞"，也就是 fail closed —— 绝不因为缺数据而放行一笔退款。
     */
    public boolean stalledAtLeast(long thresholdHours) {
        return stalledHours != null && stalledHours >= thresholdHours;
    }
}
