package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityReasonCode;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
import com.seventeen17.commerceagent.logistics.LogisticsEvent;
import com.seventeen17.commerceagent.logistics.LogisticsEventRepository;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.AfterSalesStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
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
 * T020：eligibility 的"外壳"部分 —— 规则确实来自权威存储、ownership 口径被继承、依赖故障不被吞成业务结论。
 *
 * <p>纯决策逻辑由 {@code EligibilityServiceTest} 逐条钉死，那个测试不连数据库。这里补的是只有真实
 * PostgreSQL 才能证明的三件事：
 *
 * <ol>
 *   <li><b>规则是数据，不是常量。</b>决策引用的 ruleCode/ruleVersion 必须来自 {@code commerce.after_sales_rules}
 *       的真实行，并且同一 ruleCode 的多个版本共存时取最新版本。用 mock 仓储测这条只能证明"mock 和它自己一致"。
 *   <li><b>新的读入口继承 T019 的 concealment 口径。</b>eligibility 是一个新入口；如果它自己写一遍归属判断，
 *       就会成为绕过"越权与不存在不可区分"的第二条路径。
 *   <li><b>"评估无法完成"与"评估结论是不批准"不会互相伪装。</b>物流依赖缺失必须仍是可重试的 503，而已经
 *       存在售后动作必须是确定的拒绝 —— 即使运单记录根本不存在。
 * </ol>
 *
 * <p>两个刻意的隔离约定：
 *
 * <ul>
 *   <li>订单与规则都使用 T020 专属的 {@code productCategory}。Spring 会缓存上下文，因此本类有可能与
 *       {@code AfterSalesRulePersistenceTest}（用 ELECTRONICS）共用一个容器；而 T010 的测试**不清理**自己插入
 *       的规则行。若本测试也用 ELECTRONICS，两行都无法被删除的规则会同时匹配同一订单，命中
 *       {@code CONFLICTING_RULES} —— 那是真实语义，但会让本测试变成"取决于别的测试类跑没跑过"。
 *   <li>清理只删自己造的 {@code t020-} / {@code T020-} 行，不用宽条件误伤共享数据（T018 踩过这个坑）。
 * </ul>
 *
 * <p>与 T019 一致：测试**不标注** {@code @Transactional}，否则会读到同一个持久化上下文里的缓存实体，测不出
 * 真实查询行为。
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class EligibilityServiceIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-09-20T08:00:00Z");
    private static final Instant EFFECTIVE_FROM = Instant.parse("2026-09-01T00:00:00Z");

    /** T020 专属类目，见类注释里的隔离理由。 */
    private static final String CATEGORY = "T020-CATEGORY";

    private static final String OWNER_ID = "t020-owner";
    private static final String OTHER_ID = "t020-other";
    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);
    private static final CommercePrincipal OTHER = new CommercePrincipal(OTHER_ID, UserRole.CUSTOMER);

    @Autowired
    private EligibilityService eligibilityService;

    @Autowired
    private AfterSalesRuleRepository ruleRepository;

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

    @Test
    void theDecisionIsDrivenByTheRuleRowInTheDatabase() {
        seedUser(OWNER_ID);
        seedOrder("t020-order-eligible", OrderStatus.SHIPPED, new BigDecimal("199.00"), null);
        seedRule("T020-STALLED", 1, OrderStatus.SHIPPED, 48, "500.00", "300.00");
        seedStalledShipment("t020-ship-eligible", "t020-order-eligible", Duration.ofHours(120));

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "t020-order-eligible");

        assertTrue(decision.eligible());
        assertEquals(AllowedAction.REFUND_ONLY, decision.allowedAction());
        assertEquals("T020-STALLED", decision.ruleCode(), "决策必须引用真实存在的规则行，而不是代码里的常量");
        assertEquals(1, decision.ruleVersion());
        assertEquals(0, decision.maxRefundAmount().compareTo(new BigDecimal("199.00")));
        assertFalse(decision.approvalRequired());
        assertEquals(List.of(EligibilityReasonCode.STALL_THRESHOLD_MET), decision.reasonCodes());
        assertEquals(NOW, decision.evaluatedAt());
    }

    @Test
    void theNewestActiveVersionInTheDatabaseWins() {
        seedUser(OWNER_ID);
        seedOrder("t020-order-versioned", OrderStatus.SHIPPED, new BigDecimal("199.00"), null);
        // v1 的上限 100.00 会把 199.00 判为超额；v2 的上限 500.00 才允许。结论能区分"用了哪一行"。
        seedRule("T020-VERSIONED", 1, OrderStatus.SHIPPED, 48, "100.00", "300.00");
        seedRule("T020-VERSIONED", 2, OrderStatus.SHIPPED, 48, "500.00", "300.00");
        seedStalledShipment("t020-ship-versioned", "t020-order-versioned", Duration.ofHours(120));

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "t020-order-versioned");

        assertEquals(2, decision.ruleVersion());
        assertTrue(decision.eligible(), "取到旧版本会把一笔本该可退的订单判成超额");
    }

    @Test
    void crossOwnerEvaluationIsIndistinguishableFromAMissingOrder() {
        seedUser(OWNER_ID);
        seedUser(OTHER_ID);
        seedOrder("t020-order-owned", OrderStatus.SHIPPED, new BigDecimal("199.00"), null);
        seedRule("T020-STALLED", 1, OrderStatus.SHIPPED, 48, "500.00", "300.00");

        BusinessException notMine =
                assertThrows(BusinessException.class, () -> eligibilityService.evaluate(OTHER, "t020-order-owned"));
        BusinessException missing =
                assertThrows(BusinessException.class, () -> eligibilityService.evaluate(OTHER, "t020-order-missing"));

        assertEquals(ErrorCode.ORDER_NOT_FOUND, notMine.getErrorCode());
        assertEquals(ErrorCode.ORDER_NOT_FOUND, missing.getErrorCode());
        assertEquals(missing.getMessage(), notMine.getMessage(), "新的读入口不得重新引入存在性泄露");
    }

    @Test
    void missingAuthoritativeLogisticsStaysARetryableDependencyFailure() {
        seedUser(OWNER_ID);
        seedOrder("t020-order-no-shipment", OrderStatus.SHIPPED, new BigDecimal("199.00"), null);
        seedRule("T020-STALLED", 1, OrderStatus.SHIPPED, 48, "500.00", "300.00");

        BusinessException failure = assertThrows(
                BusinessException.class, () -> eligibilityService.evaluate(OWNER, "t020-order-no-shipment"));

        // "没有权威物流记录"是暂时不可用，不是"业务上不允许退款"。把它变成一个拒绝决策，会让 Agent 把一次
        // 依赖故障当成终局结论，永久性地不退款。
        assertEquals(ErrorCode.LOGISTICS_UNAVAILABLE, failure.getErrorCode());
        assertTrue(failure.getErrorCode().retryable());
    }

    @Test
    void anOrderThatAlreadyStartedAfterSalesIsDeniedWithoutReadingLogistics() {
        seedUser(OWNER_ID);
        seedOrder(
                "t020-order-duplicate",
                OrderStatus.SHIPPED,
                new BigDecimal("199.00"),
                AfterSalesStatus.REFUND_REQUESTED);
        seedRule("T020-STALLED", 1, OrderStatus.SHIPPED, 48, "500.00", "300.00");
        // 刻意不建运单：若实现先去读物流，"本来就该拒绝"的请求会变成 503，Agent 会去重试一个永远没有结果的依赖。

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "t020-order-duplicate");

        assertEquals(AllowedAction.DENY, decision.allowedAction());
        assertEquals(List.of(EligibilityReasonCode.ORDER_ALREADY_HAS_AFTER_SALES), decision.reasonCodes());
    }

    @Test
    void aRuleWithoutAStallRequirementDecidesWithoutAShipment() {
        seedUser(OWNER_ID);
        seedOrder("t020-order-no-stall-rule", OrderStatus.SHIPPED, new BigDecimal("199.00"), null);
        seedRule("T020-NO-STALL", 1, OrderStatus.SHIPPED, null, "500.00", null);

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "t020-order-no-stall-rule");

        assertTrue(decision.eligible(), "规则不需要物流证据时，缺运单不应把一次可确定性回答的评估变成依赖故障");
        assertEquals("T020-NO-STALL", decision.ruleCode());
    }

    @Test
    void repeatedEvaluationOfTheSameAuthoritativeStateIsIdentical() {
        seedUser(OWNER_ID);
        seedOrder("t020-order-repeated", OrderStatus.SHIPPED, new BigDecimal("400.00"), null);
        seedRule("T020-STALLED", 1, OrderStatus.SHIPPED, 48, "500.00", "300.00");
        seedStalledShipment("t020-ship-repeated", "t020-order-repeated", Duration.ofHours(120));

        EligibilityDecision first = eligibilityService.evaluate(OWNER, "t020-order-repeated");
        EligibilityDecision second = eligibilityService.evaluate(OWNER, "t020-order-repeated");

        assertEquals(first, second);
        assertTrue(first.approvalRequired(), "400.00 达到 300.00 审批阈值：资格允许但必须先取得权威审批");
        assertEquals(
                List.of(EligibilityReasonCode.STALL_THRESHOLD_MET, EligibilityReasonCode.APPROVAL_REQUIRED_BY_AMOUNT),
                first.reasonCodes());
    }

    @AfterEach
    void removeT020Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't020-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code LIKE 'T020-%'");
    }

    private void seedUser(String userId) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.save(User.create(userId, userId + "-username", UserRole.CUSTOMER));
        }
    }

    private void seedOrder(
            String orderId, OrderStatus status, BigDecimal totalAmount, AfterSalesStatus afterSalesStatus) {
        Order order = Order.create(orderId, OWNER_ID, status, totalAmount, "USD");
        order.addItem(OrderItem.create(
                orderId + "-item-1", orderId + "-product-1", "Test Product", CATEGORY, totalAmount, 1));
        order.setAfterSalesStatus(afterSalesStatus);
        orderRepository.save(order);
    }

    private void seedStalledShipment(String shipmentId, String orderId, Duration stalledFor) {
        Shipment shipment =
                Shipment.create(shipmentId, orderId, "T020", shipmentId + "-tracking", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(stalledFor));
        shipmentRepository.save(shipment);
        logisticsEventRepository.save(
                LogisticsEvent.create(shipment, "IN_TRANSIT", "T020 synthetic event", NOW.minus(stalledFor)));
    }

    private void seedRule(
            String ruleCode,
            int version,
            OrderStatus requiredOrderStatus,
            Integer stalledHours,
            String maxRefundAmount,
            String approvalThreshold) {
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                ruleCode,
                version,
                CATEGORY,
                requiredOrderStatus,
                stalledHours,
                7,
                amount(maxRefundAmount),
                amount(approvalThreshold),
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null));
    }

    private static BigDecimal amount(String value) {
        return value == null ? null : new BigDecimal(value);
    }

    /** 与 T019 相同的做法：把"现在"钉死，判定与阈值比较才能精确断言。 */
    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
