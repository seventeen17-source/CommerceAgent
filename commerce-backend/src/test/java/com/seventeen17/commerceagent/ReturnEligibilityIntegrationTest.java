package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
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
import java.time.Duration;
import java.time.Instant;
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
 *   <li>A delivered order must never be granted a direct refund. True before T039 (no rule grants one)
 *       and still true after it (the granted action is a return action), so it is a regression guard
 *       rather than a placeholder waiting to be rewritten.
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
    void aDeliveredOrderIsNotEligibleForADirectRefund() {
        seedUser(OWNER_ID);
        seedOrder("T036-order-delivered-direct", OrderStatus.DELIVERED);
        seedDirectRefundRule("T036-direct-refund-direct", 1);

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "T036-order-delivered-direct");

        // A fact about the decision rather than a code path: whatever else it decides, it must not hand
        // a delivered order a direct refund.
        assertFalse(
                decision.eligible() && decision.allowedAction() == AllowedAction.REFUND_ONLY,
                "a delivered order must never be granted a direct refund");
    }

    @Test
    void aDeliveredOrderIsRoutedToAReturnAction() {
        seedUser(OWNER_ID);
        seedOrder("T036-order-delivered-return", OrderStatus.DELIVERED);
        // 这条订单还没有任何售后动作。null 才是"还没开始"，而带一个值时决策会（正确地）在第一步就以
        // ORDER_ALREADY_HAS_AFTER_SALES 拒绝 —— 那条分支没错，错的是夹具：它把"已签收、尚未申请任何售后"
        // 写成了"已有售后动作"。这也是 reasonCodes 值得被断言的原因：它一次就说清了是谁的问题。
        Order order = orderRepository.findById("T036-order-delivered-return").orElseThrow();
        order.setAfterSalesStatus(null);
        orderRepository.save(order);
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
        order.setAfterSalesStatus(AfterSalesStatus.REFUND_REQUESTED);
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

    /** The configuration US2 forbids: a direct refund granted on the delivered status itself. */
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
