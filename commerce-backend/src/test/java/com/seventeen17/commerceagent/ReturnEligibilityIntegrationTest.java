package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
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
import java.time.Instant;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/**
 * T036 — the US2 prohibition, written before the return path exists.
 *
 * <p>A delivered order must not be refunded directly; it belongs on the return path. This pins that
 * at the layer which exists today (the deterministic eligibility rules) and states the part that does
 * not exist yet as a disabled expectation rather than as a comment.
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
    private UserRepository userRepository;

    @Test
    void aDeliveredOrderIsNotEligibleForADirectRefund() {
        seedUser(OWNER_ID);
        seedOrder("T036-order-delivered-direct", OrderStatus.DELIVERED);
        seedDirectRefundRule("T036-direct-refund-direct", 1);

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "T036-order-delivered-direct");

        // A fact about the decision, not about a code path: whatever else it decides, it must not hand
        // a delivered order a direct refund. True today (no rule grants one) and after T039 (the
        // granted action becomes a return action).
        assertFalse(
                decision.eligible() && decision.allowedAction() == AllowedAction.REFUND_ONLY,
                "a delivered order must never be granted a direct refund");
    }

    @Test
    @Disabled("T039/T041 落地后启用：已签收应被路由到退货类动作")
    void aDeliveredOrderIsRoutedToAReturnAction() {
        seedUser(OWNER_ID);
        seedOrder("T036-order-delivered-return", OrderStatus.DELIVERED);
        seedDirectRefundRule("T036-direct-refund-return", 2);

        EligibilityDecision decision = eligibilityService.evaluate(OWNER, "T036-order-delivered-return");

        assertTrue(decision.eligible());
        assertTrue(decision.allowedAction() == AllowedAction.RETURN
                || decision.allowedAction() == AllowedAction.RETURN_REFUND);
    }

    private void seedUser(String userId) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.save(User.create(userId, userId + "-username", UserRole.CUSTOMER));
        }
    }

    private void seedOrder(String orderId, OrderStatus status) {
        Order order = Order.create(orderId, OWNER_ID, status, amount("120.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item-1", orderId + "-product-1", "Test Product", CATEGORY, amount("120.00"), 1));
        order.setAfterSalesStatus(AfterSalesStatus.REFUND_REQUESTED);
        orderRepository.save(order);
    }

    /** The configuration US2 forbids: a direct refund granted on the delivered status itself. */
    private void seedDirectRefundRule(String ruleCode, int version) {
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                ruleCode,
                version,
                CATEGORY,
                OrderStatus.DELIVERED,
                null,
                7,
                amount("500.00"),
                amount("1000.00"),
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null));
    }

    private static BigDecimal amount(String value) {
        return value == null ? null : new BigDecimal(value);
    }
}
