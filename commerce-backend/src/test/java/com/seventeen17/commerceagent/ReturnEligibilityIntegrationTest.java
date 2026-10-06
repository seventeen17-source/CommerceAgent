package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityReasonCode;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * T036 + T039 — the US2 prohibition, and the permission that replaces it.
 *
 * <p>Two assertions about a delivered order, deliberately different in kind:
 *
 * <ul>
 *   <li>A delivered order must never be granted a direct refund — not even when a rule row says it should.
 *       True before T039 (no rule granted one) and still true after it, so it is a regression guard rather
 *       than a placeholder waiting to be rewritten. Since T036's guard the decision enforces it itself, and
 *       the refusal names the conflict ({@code DELIVERED_ORDER_IS_RETURN_ONLY}) instead of hiding behind a
 *       generic "not eligible".
 *   <li>A delivered order inside the return window is granted a return action. This one only became
 *       true with T039, and it is the half that proves the feature does something: a suite of
 *       refusals alone stays green while every real return is still answered with "no".
 * </ul>
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class ReturnEligibilityIntegrationTest {

    private static final Instant EFFECTIVE_FROM = Instant.parse("2026-09-01T00:00:00Z");

    private static final String CATEGORY = "T036-CATEGORY";

    private static final String OWNER_ID = "t036-owner";

    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);

    @Autowired
    private EligibilityService eligibilityService;

    @Autowired
    private AfterSalesRuleRepository ruleRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private UserRepository userRepository;

    /**
     * Both tests seed a rule for the same category and the same delivered status, and rule selection
     * treats two different rule codes in that position as a conflict rather than a choice. Without
     * this, the first test's rule decides the second test's outcome — which reads exactly like a
     * broken implementation while actually being one test inheriting another test's world.
     */
    @AfterEach
    void removeT036State() {
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code LIKE 'T036-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 'T036-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 'T036-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 'T036-%'");
    }

    @Test
    void aDeliveredOrderIsNotEligibleForADirectRefundWhateverTheRuleSays() {
        seedUser(OWNER_ID);
        // 这张订单**没有任何售后动作**（seedOrder 不再伪造一个）：这是本用例能不能成立的前提。夹具一旦把订单
        // 写成"已有售后动作"，决策会在第一步以 ORDER_ALREADY_HAS_AFTER_SALES 拒绝 —— 测试仍然绿，而它声称
        // 要守的那条不变量（已签收不得被直接退款）根本没被执行过。
        seedOrder("T036-order-delivered-direct", OrderStatus.DELIVERED);
        seedDirectRefundRule("T036-direct-refund-direct", 1);

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "T036-order-delivered-direct");

        // 断言的是"决策的事实"而不是某条代码路径：无论它怎么绕，都不能把直接退款交给一张已签收的订单。
        assertFalse(decision.eligible(), "已签收订单不得被 REFUND_ONLY 放行");
        assertNotEquals(AllowedAction.REFUND_ONLY, decision.allowedAction());
        assertFalse(decision.grantsMoneyAction(), "一张已签收的订单不能在这里拿到资金动作");
        // 具名原因码，而不是"反正不批"：它一次说清是谁的问题 —— 规则声明的动作与订单状态不相容。
        assertEquals(List.of(EligibilityReasonCode.DELIVERED_ORDER_IS_RETURN_ONLY), decision.reasonCodes());
    }

    @Test
    void aDeliveredOrderIsRoutedToAReturnAction() {
        seedUser(OWNER_ID);
        // 这张订单同样没有任何售后动作：null 表示"还没开始"，也正是退货窗口该被评估的那个起点。
        seedOrder("T036-order-delivered-return", OrderStatus.DELIVERED);
        seedReturnRule("T036-return-open", 1, 7);
        seedSignedShipment("T036-shipment-open", "T036-order-delivered-return", Duration.ofDays(3));

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "T036-order-delivered-return");

        assertTrue(
                decision.eligible(),
                "签收 3 天、窗口 7 天：应当放行退货，但实际 reasonCodes=" + decision.reasonCodes() + " action="
                        + decision.allowedAction());
        assertTrue(
                decision.allowedAction() == AllowedAction.RETURN
                        || decision.allowedAction() == AllowedAction.RETURN_REFUND,
                "已签收订单被放行的动作必须是退货类，实际是 " + decision.allowedAction());
    }

    private void seedUser(String userId) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.save(User.create(userId, userId + "-username", UserRole.CUSTOMER));
        }
    }

    private void seedOrder(String orderId, OrderStatus status) {
        if (orderRepository.findById(orderId).isPresent()) {
            return;
        }
        Order order = Order.create(orderId, OWNER_ID, status, amount("120.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item-1", orderId + "-product-1", "Test Product", CATEGORY, amount("120.00"), 1));
        // 刻意不写 afterSalesStatus：null 表示"这张订单还没有任何售后动作"，那是两个用例都需要的起点。
        // 曾经这里写过 REFUND_REQUESTED，于是负例在决策的第一步（ORDER_ALREADY_HAS_AFTER_SALES）就被拦下，
        // "已签收不得直接退款"这条断言在夹具撒谎的情况下一直为真，而真正的守卫从未被触发过。
        orderRepository.save(order);
    }

    /**
     * A shipment the carrier says was signed for, {@code signedFor} ago — the return window's starting
     * point. {@code shipments.signed_at} is the fact this repository already treats as "delivered"
     * (see {@code LogisticsStallCalculator.isSigned}), which is why T039 reads it rather than an order
     * column that no production path writes.
     */
    private void seedSignedShipment(String shipmentId, String orderId, Duration signedFor) {
        Shipment shipment =
                Shipment.create(shipmentId, orderId, "T036", shipmentId + "-tracking", ShipmentStatus.DELIVERED);
        shipment.setSignedAt(Instant.now().minus(signedFor));
        shipmentRepository.save(shipment);
    }

    /**
     * The configuration US2 forbids: a direct refund granted on the delivered status itself.
     *
     * <p>It exists to <em>trigger</em> the guard, not to describe a permitted setup: the decision must refuse it
     * on its own, which is what {@code DELIVERED_ORDER_IS_RETURN_ONLY} reports. That only holds while the order
     * has no after-sales action yet — an existing one would short-circuit the decision before the guard is ever
     * consulted, and the test would pass while testing nothing.
     */
    private void seedDirectRefundRule(String ruleCode, int version) {
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                ruleCode,
                version,
                CATEGORY,
                OrderStatus.DELIVERED,
                null,
                null,
                amount("500.00"),
                amount("1000.00"),
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null));
    }

    /**
     * The configuration US2 wants: a delivered order may be <em>returned</em> inside a window.
     *
     * <p>Note {@code logisticsStalledHours = null}. A return rule must not declare a stall threshold:
     * a signed shipment would then trip the stall branch's conflict check
     * ({@code LOGISTICS_CONFLICTS_WITH_ORDER}) and send every legitimate return to manual review.
     */
    private void seedReturnRule(String ruleCode, int version, int returnWindowDays) {
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                ruleCode,
                version,
                CATEGORY,
                OrderStatus.DELIVERED,
                null,
                returnWindowDays,
                amount("500.00"),
                amount("1000.00"),
                AllowedAction.RETURN_REFUND,
                true,
                EFFECTIVE_FROM,
                null));
    }

    private static BigDecimal amount(String value) {
        return value == null ? null : new BigDecimal(value);
    }
}
