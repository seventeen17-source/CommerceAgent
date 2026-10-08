package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.seventeen17.commerceagent.approval.ApprovalRequest;
import com.seventeen17.commerceagent.approval.ApprovalRequestRepository;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.refund.RefundCommand;
import com.seventeen17.commerceagent.refund.RefundRequestRepository;
import com.seventeen17.commerceagent.refund.RefundService;
import com.seventeen17.commerceagent.returns.ReturnCommand;
import com.seventeen17.commerceagent.returns.ReturnRequestRepository;
import com.seventeen17.commerceagent.returns.ReturnService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
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

/** T054 executable proof that an approval id is never a bearer token at the final Java write. */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, ApprovalWriteBindingIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
class ApprovalWriteBindingIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-10-08T08:00:00Z");
    private static final String OWNER_ID = "t054-owner";
    private static final String APPROVER_ID = "t054-approver";
    private static final String RUN_ID = "54000000-0000-4000-8000-000000000001";
    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);
    private static final CommercePrincipal APPROVER = new CommercePrincipal(APPROVER_ID, UserRole.APPROVER);

    @Autowired
    private RefundService refundService;

    @Autowired
    private ReturnService returnService;

    @Autowired
    private RefundRequestRepository refundRepository;

    @Autowired
    private ReturnRequestRepository returnRepository;

    @Autowired
    private ApprovalRequestRepository approvalRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private AfterSalesRuleRepository ruleRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void exactApprovedRefundBindingUnlocksOnlyItsOwnWrite() {
        seedRefundOrder("t054-refund-order");
        seedApproved(
                "t054-refund-approval",
                RUN_ID,
                "t054-refund-order",
                AllowedAction.REFUND_ONLY,
                new BigDecimal("400.00"),
                "T054-REFUND");

        refundService.createRefund(
                OWNER,
                "t054refundkey",
                new RefundCommand(
                        "t054-refund-order",
                        "STALLED_LOGISTICS",
                        null,
                        "t054-refund-approval",
                        RUN_ID));

        var refund = refundRepository.findByUserIdAndIdempotencyKey(OWNER_ID, "t054refundkey").orElseThrow();
        assertEquals("t054-refund-approval", refund.getApprovalRequestId());
    }

    @Test
    void approvedRefundFromAnotherRunIsRejectedBeforeMoneyMoves() {
        seedRefundOrder("t054-cross-run-order");
        seedApproved(
                "t054-cross-run-approval",
                "54000000-0000-4000-8000-000000000099",
                "t054-cross-run-order",
                AllowedAction.REFUND_ONLY,
                new BigDecimal("400.00"),
                "T054-REFUND");

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> refundService.createRefund(
                        OWNER,
                        "t054crossrun",
                        new RefundCommand(
                                "t054-cross-run-order",
                                "STALLED_LOGISTICS",
                                null,
                                "t054-cross-run-approval",
                                RUN_ID)));

        assertEquals(ErrorCode.APPROVAL_CONFLICT, failure.getErrorCode());
        assertEquals(0, countRefunds("t054-cross-run-order"));
    }

    @Test
    void exactApprovedReturnRefundBindingUnlocksTheReturnWrite() {
        seedDeliveredReturnRefundOrder("t054-return-order");
        seedApproved(
                "t054-return-approval",
                RUN_ID,
                "t054-return-order",
                AllowedAction.RETURN_REFUND,
                new BigDecimal("400.00"),
                "T054-RETURN");

        returnService.createReturn(
                OWNER,
                "t054returnkey",
                new ReturnCommand(
                        "t054-return-order",
                        "DELIVERED_RETURN",
                        null,
                        "t054-return-approval",
                        RUN_ID));

        var request = returnRepository
                .findByUserIdAndIdempotencyKey(OWNER_ID, "t054returnkey")
                .orElseThrow();
        assertEquals("t054-return-approval", request.getApprovalRequestId());
    }

    @Test
    void approvedRecordForAnotherActionCannotUnlockTheReturnWrite() {
        seedDeliveredReturnRefundOrder("t054-cross-action-order");
        seedApproved(
                "t054-cross-action-approval",
                RUN_ID,
                "t054-cross-action-order",
                AllowedAction.REFUND_ONLY,
                new BigDecimal("400.00"),
                "T054-RETURN");

        BusinessException failure = assertThrows(
                BusinessException.class,
                () -> returnService.createReturn(
                        OWNER,
                        "t054crossaction",
                        new ReturnCommand(
                                "t054-cross-action-order",
                                "DELIVERED_RETURN",
                                null,
                                "t054-cross-action-approval",
                                RUN_ID)));

        assertEquals(ErrorCode.APPROVAL_CONFLICT, failure.getErrorCode());
        assertEquals(0, countReturns("t054-cross-action-order"));
    }

    private void seedRefundOrder(String orderId) {
        seedUsers();
        Order order = Order.create(orderId, OWNER_ID, OrderStatus.SHIPPED, new BigDecimal("400.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item", orderId + "-product", "T054 Refund", "T054_REFUND", new BigDecimal("400.00"), 1));
        orderRepository.saveAndFlush(order);
        Shipment shipment = Shipment.create(
                orderId + "-shipment", orderId, "T054", orderId + "-tracking", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(Duration.ofHours(72)));
        shipmentRepository.saveAndFlush(shipment);
        if (ruleRepository.findByRuleCodeAndVersion("T054-REFUND", 1).isEmpty()) {
            ruleRepository.saveAndFlush(AfterSalesRule.create(
                    "T054-REFUND", 1, "T054_REFUND", OrderStatus.SHIPPED, 48, 7,
                    new BigDecimal("500.00"), new BigDecimal("300.00"),
                    AllowedAction.REFUND_ONLY, true, NOW.minus(Duration.ofDays(30)), null));
        }
    }

    private void seedDeliveredReturnRefundOrder(String orderId) {
        seedUsers();
        Order order = Order.create(orderId, OWNER_ID, OrderStatus.DELIVERED, new BigDecimal("400.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item", orderId + "-product", "T054 Return", "T054_RETURN", new BigDecimal("400.00"), 1));
        orderRepository.saveAndFlush(order);
        Shipment shipment = Shipment.create(
                orderId + "-shipment", orderId, "T054", orderId + "-tracking", ShipmentStatus.DELIVERED);
        shipment.setSignedAt(NOW.minus(Duration.ofDays(2)));
        shipmentRepository.saveAndFlush(shipment);
        if (ruleRepository.findByRuleCodeAndVersion("T054-RETURN", 1).isEmpty()) {
            ruleRepository.saveAndFlush(AfterSalesRule.create(
                    "T054-RETURN", 1, "T054_RETURN", OrderStatus.DELIVERED, null, 7,
                    new BigDecimal("500.00"), new BigDecimal("300.00"),
                    AllowedAction.RETURN_REFUND, true, NOW.minus(Duration.ofDays(30)), null));
        }
    }

    private void seedUsers() {
        if (userRepository.findById(OWNER_ID).isEmpty()) {
            userRepository.saveAndFlush(User.create(OWNER_ID, OWNER_ID, UserRole.CUSTOMER));
        }
        if (userRepository.findById(APPROVER_ID).isEmpty()) {
            userRepository.saveAndFlush(User.create(APPROVER_ID, APPROVER_ID, UserRole.APPROVER));
        }
    }

    private void seedApproved(
            String id,
            String runId,
            String orderId,
            AllowedAction action,
            BigDecimal amount,
            String ruleCode) {
        ApprovalRequest approval = ApprovalRequest.pending(
                id,
                runId,
                orderId,
                OWNER_ID,
                action,
                amount,
                ruleCode,
                "APPROVAL_REQUIRED_BY_AMOUNT",
                NOW.plus(Duration.ofHours(1)));
        approval.approve(APPROVER, NOW);
        approvalRepository.saveAndFlush(approval);
    }

    private int countRefunds(String orderId) {
        Integer value = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM commerce.refund_requests WHERE order_id = ?", Integer.class, orderId);
        return value == null ? 0 : value;
    }

    private int countReturns(String orderId) {
        Integer value = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM commerce.return_requests WHERE order_id = ?", Integer.class, orderId);
        return value == null ? 0 : value;
    }

    @AfterEach
    void cleanUp() {
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id IN "
                        + "(SELECT id FROM commerce.refund_requests WHERE order_id LIKE 't054-%')");
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id IN "
                        + "(SELECT id FROM commerce.return_requests WHERE order_id LIKE 't054-%')");
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id IN "
                        + "(SELECT id FROM commerce.approval_requests WHERE order_id LIKE 't054-%')");
        jdbcTemplate.update("DELETE FROM commerce.refund_requests WHERE order_id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.return_requests WHERE order_id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.approval_requests WHERE order_id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't054-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code LIKE 'T054-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't054-%'");
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {
        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
