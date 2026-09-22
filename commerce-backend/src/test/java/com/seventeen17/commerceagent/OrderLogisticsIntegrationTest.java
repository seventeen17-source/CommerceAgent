package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditLog;
import com.seventeen17.commerceagent.audit.AuditLogRepository;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.logistics.LogisticsEvent;
import com.seventeen17.commerceagent.logistics.LogisticsEventRepository;
import com.seventeen17.commerceagent.logistics.LogisticsService;
import com.seventeen17.commerceagent.logistics.LogisticsSnapshot;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.order.OrderSnapshot;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.order.OrderSummary;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * T019：ownership-scoped order/logistics read 与权威 stall calculation 的可执行规格。
 *
 * <p>本测试要钉死的是**两个容易被写"对"但语义写错**的地方：
 *
 * <h2>1. 越权读必须"对外不可区分"</h2>
 *
 * {@code findByIdAndOwnerId} 把"订单不存在"和"订单属于别人"合并成了一个 {@code Optional.empty()}。这是刻意的：
 * 若对别人的订单回 403、对不存在的 id 回 404，攻击者就能用状态码差异把哪些 orderId 真实存在枚举出来。本项目
 * fixture 的 id 形如 {@code order-001}，可枚举，所以
 * {@link #anotherUsersOrderIsIndistinguishableFromAMissingOrder()} 不只断言错误码相同，还断言**消息逐字相同**——
 * 将来谁想加一句"更友好"的提示，都会被这条断言拦住。
 *
 * <h2>2. 停滞计算的口径必须确定，且失败方向要选对</h2>
 *
 * 停滞时长的每个口径选择都会影响钱：基准取哪个时间戳、缺证据时算 0 还是算"不知道"、小数点往哪边取整、已签收
 * 订单还算不算停滞。这些**不能靠代码读起来"感觉对"**，所以每一项都有一条独立用例：
 *
 * <ul>
 *   <li>{@link #stallBaselineTakesWhicheverSourceIsMoreRecent()}：投影列与事件表漂移时取较近的一个（低估停滞）；
 *   <li>{@link #missingLogisticsEvidenceYieldsUnknownInsteadOfZeroHours()}：没有证据时返回 null 而不是 0；
 *   <li>{@link #stallThresholdComparisonTruncatesDownwards()}：47h59m 不算达标，整 48h 才算；
 *   <li>{@link #signedLogisticsHasNoStallEvenWhenTheLastEventIsOld()}：已签收订单不存在"物流停滞"；
 *   <li>{@link #orderWithoutShipmentRecordFailsClosedInsteadOfInventingLogistics()}：无运单时明确 503，不返回空快照。
 * </ul>
 *
 * <p>测试**不标注** {@code @Transactional}（与 T009 的并发测试一致）：每个仓储调用都必须跑在自己的事务里，否则
 * 读到的会是同一个持久化上下文里的缓存实例，测不出真实查询行为。
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class OrderLogisticsIntegrationTest {

    /**
     * 固定的"现在"。业务代码读的是注入的 {@link Clock}，测试把它钉在这里，于是停滞时长可以做**精确**断言，
     * 而不是退化成"应该大于 48 吧"这种会随时间腐烂的模糊断言。
     */
    private static final Instant NOW = Instant.parse("2026-09-20T08:00:00Z");

    private static final String OWNER_ID = "t019-owner";
    private static final String OTHER_ID = "t019-other";
    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);
    private static final CommercePrincipal OTHER = new CommercePrincipal(OTHER_ID, UserRole.CUSTOMER);

    @Autowired
    private OrderService orderService;

    @Autowired
    private LogisticsService logisticsService;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private LogisticsEventRepository logisticsEventRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private AuditLogRepository auditLogRepository;

    @Test
    void orderDetailIsReadableByItsOwner() {
        seedUser(OWNER_ID);
        seedOrder("t019-order-detail", OWNER_ID, OrderStatus.SHIPPED, 1);

        OrderSnapshot snapshot = orderService.getOrder(OWNER, "t019-order-detail");

        assertEquals("t019-order-detail", snapshot.orderId());
        assertEquals(OrderStatus.SHIPPED, snapshot.status());
        assertEquals("USD", snapshot.currency());
        assertEquals(0, snapshot.totalAmount().compareTo(new BigDecimal("199.00")));
        assertNull(snapshot.afterSalesStatus(), "尚无售后动作时必须保持 null，而不是编一个占位状态");
        assertEquals(1, snapshot.items().size());
        assertEquals("Test Product", snapshot.items().get(0).productName());
    }

    @Test
    void anotherUsersOrderIsIndistinguishableFromAMissingOrder() {
        seedUser(OWNER_ID);
        seedUser(OTHER_ID);
        seedOrder("t019-order-owned-by-owner", OWNER_ID, OrderStatus.SHIPPED, 1);

        BusinessException notMine =
                assertThrows(BusinessException.class, () -> orderService.getOrder(OTHER, "t019-order-owned-by-owner"));
        BusinessException missing =
                assertThrows(BusinessException.class, () -> orderService.getOrder(OTHER, "t019-order-does-not-exist"));

        assertEquals(ErrorCode.ORDER_NOT_FOUND, notMine.getErrorCode());
        assertEquals(ErrorCode.ORDER_NOT_FOUND, missing.getErrorCode());
        // 关键断言：两条路径的对外表达必须逐字相同。任何措辞差异都会重新变成"这个 id 真实存在"的信息泄露。
        assertEquals(missing.getMessage(), notMine.getMessage());
    }

    @Test
    void orderListNeverContainsAnotherUsersOrders() {
        seedUser(OWNER_ID);
        seedUser(OTHER_ID);
        seedOrder("t019-order-mine", OWNER_ID, OrderStatus.SHIPPED, 1);
        seedOrder("t019-order-theirs", OTHER_ID, OrderStatus.SHIPPED, 1);

        List<OrderSummary> ownOrders = orderService.listOwnOrders(OWNER);

        // 断言整个集合，而不是"不含某人"这种否定式：集合是 ownership 过滤最强的证据。
        assertEquals(
                List.of("t019-order-mine"),
                ownOrders.stream().map(OrderSummary::orderId).toList());
        assertNotNull(ownOrders.get(0).createdAt());
    }

    @Test
    void logisticsReadIsAlsoGatedByOwnership() {
        seedUser(OWNER_ID);
        seedUser(OTHER_ID);
        seedOrder("t019-order-logistics-guard", OWNER_ID, OrderStatus.SHIPPED, 1);
        seedShipment(
                "t019-ship-guard",
                "t019-order-logistics-guard",
                ShipmentStatus.IN_TRANSIT,
                NOW.minus(Duration.ofHours(120)),
                null);

        assertNotNull(logisticsService.getLogistics(OWNER, "t019-order-logistics-guard"));

        BusinessException denied = assertThrows(
                BusinessException.class, () -> logisticsService.getLogistics(OTHER, "t019-order-logistics-guard"));
        assertEquals(ErrorCode.ORDER_NOT_FOUND, denied.getErrorCode(), "物流轨迹也是敏感数据：越权读物流必须走与越权读订单完全相同的失败语义");
    }

    @Test
    void stalledHoursIsMeasuredFromTheLatestAuthoritativeLogisticsEvidence() {
        seedStalledOrder("t019-order-stalled", "t019-ship-stalled", Duration.ofHours(120), Duration.ofHours(120));

        LogisticsSnapshot snapshot = logisticsService.getLogistics(OWNER, "t019-order-stalled");

        assertEquals(NOW.minus(Duration.ofHours(120)), snapshot.lastMeaningfulEventAt());
        assertEquals(Long.valueOf(120L), snapshot.stalledHours());
        assertFalse(snapshot.signed());
        assertEquals(ShipmentStatus.IN_TRANSIT, snapshot.status());
        assertTrue(snapshot.stalledAtLeast(48));
    }

    @Test
    void stallBaselineTakesWhicheverSourceIsMoreRecent() {
        // 投影列比事件表旧 70 小时：只看 shipments.last_event_at 会算出 100 小时停滞，从而虚报停滞。
        seedStalledOrder(
                "t019-order-drift-old-projection", "t019-ship-drift-1", Duration.ofHours(100), Duration.ofHours(30));
        LogisticsSnapshot fromEvent = logisticsService.getLogistics(OWNER, "t019-order-drift-old-projection");
        assertEquals(NOW.minus(Duration.ofHours(30)), fromEvent.lastMeaningfulEventAt());
        assertEquals(Long.valueOf(30L), fromEvent.stalledHours());

        // 反向漂移：事件表更旧，结论必须一样 —— 取"最近一次确实有过的动静"。
        seedStalledOrder(
                "t019-order-drift-old-event", "t019-ship-drift-2", Duration.ofHours(30), Duration.ofHours(100));
        LogisticsSnapshot fromProjection = logisticsService.getLogistics(OWNER, "t019-order-drift-old-event");
        assertEquals(NOW.minus(Duration.ofHours(30)), fromProjection.lastMeaningfulEventAt());
        assertEquals(Long.valueOf(30L), fromProjection.stalledHours());
    }

    @Test
    void signedLogisticsHasNoStallEvenWhenTheLastEventIsOld() {
        seedUser(OWNER_ID);
        seedOrder("t019-order-signed", OWNER_ID, OrderStatus.DELIVERED, 1);
        seedShipment(
                "t019-ship-signed",
                "t019-order-signed",
                ShipmentStatus.DELIVERED,
                NOW.minus(Duration.ofHours(120)),
                NOW.minus(Duration.ofHours(120)));

        LogisticsSnapshot snapshot = logisticsService.getLogistics(OWNER, "t019-order-signed");

        assertTrue(snapshot.signed());
        assertNull(snapshot.stalledHours(), "已签收订单不存在'物流停滞'：这条证据若成立，US2 的退货路径会被 US1 的退款路径抢走");
        assertEquals(NOW.minus(Duration.ofHours(120)), snapshot.lastMeaningfulEventAt());
        assertFalse(snapshot.stalledAtLeast(48));
    }

    @Test
    void shipmentStatusAloneIsEnoughToTreatADeliveredShipmentAsSigned() {
        // 状态已 DELIVERED、但签收时间没落库：两个来源冲突时按已签收处理（少退款的方向）。
        seedUser(OWNER_ID);
        seedOrder("t019-order-status-only", OWNER_ID, OrderStatus.DELIVERED, 1);
        seedShipment(
                "t019-ship-status-only",
                "t019-order-status-only",
                ShipmentStatus.DELIVERED,
                NOW.minus(Duration.ofHours(120)),
                null);

        LogisticsSnapshot snapshot = logisticsService.getLogistics(OWNER, "t019-order-status-only");

        assertTrue(snapshot.signed());
        assertNull(snapshot.stalledHours());
    }

    @Test
    void missingLogisticsEvidenceYieldsUnknownInsteadOfZeroHours() {
        seedUser(OWNER_ID);
        seedOrder("t019-order-no-evidence", OWNER_ID, OrderStatus.SHIPPED, 1);
        seedShipment("t019-ship-no-evidence", "t019-order-no-evidence", ShipmentStatus.CREATED, null, null);

        LogisticsSnapshot snapshot = logisticsService.getLogistics(OWNER, "t019-order-no-evidence");

        assertEquals(ShipmentStatus.CREATED, snapshot.status());
        assertNull(snapshot.lastMeaningfulEventAt());
        assertNull(snapshot.stalledHours(), "'没有证据'与'停滞 0 小时'必须是两种不同的结果");
        assertFalse(snapshot.stalledAtLeast(48), "证据缺失时阈值比较必须 fail closed，而不是放行");
    }

    @Test
    void futureDatedEvidenceClampsStallToZeroAndKeepsTheRawTimestamp() {
        seedStalledOrder("t019-order-future", "t019-ship-future", Duration.ofHours(-2), Duration.ofHours(-2));

        LogisticsSnapshot snapshot = logisticsService.getLogistics(OWNER, "t019-order-future");

        // 原始事实照实暴露：调用方仍然看得见"这个时间戳在未来"这个异常，我们只是不把它算成停滞。
        assertEquals(NOW.plus(Duration.ofHours(2)), snapshot.lastMeaningfulEventAt());
        assertEquals(Long.valueOf(0L), snapshot.stalledHours());
    }

    @Test
    void stallThresholdComparisonTruncatesDownwards() {
        seedStalledOrder(
                "t019-order-just-under",
                "t019-ship-just-under",
                Duration.ofHours(47).plusMinutes(59),
                Duration.ofHours(47).plusMinutes(59));
        LogisticsSnapshot justUnder = logisticsService.getLogistics(OWNER, "t019-order-just-under");
        assertEquals(Long.valueOf(47L), justUnder.stalledHours());
        assertFalse(justUnder.stalledAtLeast(48), "47 小时 59 分不能算作达到 48 小时阈值");

        seedStalledOrder("t019-order-exactly", "t019-ship-exactly", Duration.ofHours(48), Duration.ofHours(48));
        LogisticsSnapshot exactly = logisticsService.getLogistics(OWNER, "t019-order-exactly");
        assertEquals(Long.valueOf(48L), exactly.stalledHours());
        assertTrue(exactly.stalledAtLeast(48), "阈值比较取等号：正好 48 小时算达到");
    }

    @Test
    void orderWithoutShipmentRecordFailsClosedInsteadOfInventingLogistics() {
        seedUser(OWNER_ID);
        seedOrder("t019-order-no-shipment", OWNER_ID, OrderStatus.SHIPPED, 1);

        BusinessException failure = assertThrows(
                BusinessException.class, () -> logisticsService.getLogistics(OWNER, "t019-order-no-shipment"));

        assertEquals(ErrorCode.LOGISTICS_UNAVAILABLE, failure.getErrorCode());
        assertTrue(failure.getErrorCode().retryable(), "对外是'暂时不可用'：Agent 可以在重试预算内再试，但不得据此推断物流状态后继续退款");
    }

    /**
     * 对外抹平 ≠ 内部失明：cross-owner 读在响应上与"不存在"完全一致，但必须在审计里留下**真实原因**。
     *
     * <p>这里断言的是**字面量**而不是 {@code OrderService} 里的常量：`ORDER_ACCESS_DENIED` 与 `CROSS_OWNER` 是对外
     * 可查询的契约，用字面量才能保证"有人改了常量"这件事被测试抓住，而不是测试跟着一起改。
     */
    @Test
    void crossOwnerReadIsConcealedExternallyButAuditedInternally() {
        seedUser(OWNER_ID);
        seedUser(OTHER_ID);
        seedOrder("t019-order-audited", OWNER_ID, OrderStatus.SHIPPED, 1);

        BusinessException denied =
                assertThrows(BusinessException.class, () -> orderService.getOrder(OTHER, "t019-order-audited"));
        assertEquals(ErrorCode.ORDER_NOT_FOUND, denied.getErrorCode());

        List<AuditLog> auditTrail = auditLogRepository.findByActionAndResourceIdOrderByCreatedAtAsc(
                "ORDER_ACCESS_DENIED", "t019-order-audited");
        assertEquals(1, auditTrail.size(), "cross-owner 读必须留痕：否则'谁在探测别人的订单'将永远无法被回答");

        AuditLog entry = auditTrail.get(0);
        assertEquals(AuditActorType.USER, entry.getActorType());
        assertEquals(OTHER_ID, entry.getActorId(), "审计记录的是真实的越权主体，不是订单所有者");
        assertEquals("DENIED", entry.getResult());
        assertEquals("CROSS_OWNER", entry.getMetadataJson().get("reason"));
        assertEquals("ORDER_NOT_FOUND", entry.getMetadataJson().get("concealedAs"));
    }

    /**
     * 普通 404 不是安全事件，**不得**写审计。
     *
     * <p>否则一次 id 扫描（每个不存在的 id 一条审计行）就能把审计表刷爆，把真正值得追查的越权信号淹掉——这是
     * "审计保真"与"审计可用"之间的取舍，必须由测试固定下来，而不是靠实现者自觉。
     */
    @Test
    void missingOrderDoesNotFloodTheSecurityAudit() {
        seedUser(OTHER_ID);

        assertThrows(BusinessException.class, () -> orderService.getOrder(OTHER, "t019-order-never-existed"));

        assertTrue(
                auditLogRepository
                        .findByActionAndResourceIdOrderByCreatedAtAsc("ORDER_ACCESS_DENIED", "t019-order-never-existed")
                        .isEmpty(),
                "不存在的订单不写审计：它不携带'有人越权'这个信号");
    }

    /**
     * 只删本测试自己造的行（{@code t019-} 前缀）。
     *
     * <p>刻意不用 {@code LIKE 'customer-%'} 这类宽条件：那会误伤共享开发库里的 fixture 数据（T018 已经踩过这个
     * 坑）。删除顺序按外键依赖倒着走。
     */
    @AfterEach
    void removeT019Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't019-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't019-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't019-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't019-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't019-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't019-%'");
    }

    private void seedUser(String userId) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.save(User.create(userId, userId + "-username", UserRole.CUSTOMER));
        }
    }

    private void seedOrder(String orderId, String ownerId, OrderStatus status, int itemCount) {
        Order order = Order.create(orderId, ownerId, status, new BigDecimal("199.00"), "USD");
        for (int index = 1; index <= itemCount; index++) {
            order.addItem(OrderItem.create(
                    orderId + "-item-" + index,
                    "t019-product-" + index,
                    "Test Product",
                    "ELECTRONICS",
                    new BigDecimal("199.00"),
                    1));
        }
        orderRepository.save(order);
    }

    /**
     * 造一个"投影列与事件表可以各说各话"的订单：两个偏移量分别落到 {@code shipments.last_event_at} 和
     * {@code logistics_events.occurred_at}，用来验证 {@code max()} 的两个方向。
     */
    private void seedStalledOrder(String orderId, String shipmentId, Duration projectionOffset, Duration eventOffset) {
        seedUser(OWNER_ID);
        seedOrder(orderId, OWNER_ID, OrderStatus.SHIPPED, 1);
        seedShipment(shipmentId, orderId, ShipmentStatus.IN_TRANSIT, NOW.minus(projectionOffset), null);

        Shipment shipment = shipmentRepository.findById(shipmentId).orElseThrow();
        logisticsEventRepository.save(
                LogisticsEvent.create(shipment, "IN_TRANSIT", "T019 synthetic event", NOW.minus(eventOffset)));
    }

    private void seedShipment(
            String shipmentId, String orderId, ShipmentStatus status, Instant lastEventAt, Instant signedAt) {
        Shipment shipment = Shipment.create(shipmentId, orderId, "T019", "T019-" + shipmentId, status);
        shipment.setLastEventAt(lastEventAt);
        shipment.setSignedAt(signedAt);
        shipmentRepository.save(shipment);
    }

    /**
     * 用固定时钟覆盖生产时钟。
     *
     * <p>{@code @Primary} 是必需的：容器里会同时存在 {@code ClockConfig.systemClock} 和这个 bean，测试期间由这个
     * 说了算。
     */
    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
