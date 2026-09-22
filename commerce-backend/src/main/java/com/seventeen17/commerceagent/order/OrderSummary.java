package com.seventeen17.commerceagent.order;

import java.time.Instant;

/**
 * 订单列表读模型（对应契约 {@code OrderSummary}）。
 *
 * <p>为什么不直接返回 {@link Order} 实体：读接口的消费方是 Agent，它只需要"能定位到哪一单"的最小信息。把实体
 * 交出去有两个后果——
 *
 * <ul>
 *   <li>{@code items} 是 LAZY 集合，一旦离开事务再访问就抛 {@code LazyInitializationException}
 *       （本项目配置了 {@code open-in-view: false}，没有"请求期间偷偷保持 session 打开"的兜底）；
 *   <li>实体带 setter，消费方拿到的是一个"看起来可以改"的对象，而业务状态的修改必须走有校验的写入路径。
 * </ul>
 */
public record OrderSummary(String orderId, String productSummary, OrderStatus status, Instant createdAt) {}
