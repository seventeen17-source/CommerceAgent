package com.seventeen17.commerceagent;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

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
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
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
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * T025: prove the eligibility authority survives the real HTTP boundary.
 *
 * <p>T020 already proves the pure decision functions. These cases start at MockMvc so a green test
 * proves the complete path: Bearer JWT -> Spring Security -> EligibilityController ->
 * EligibilityService -> authoritative repositories -> deterministic JSON decision/error envelope.
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, EligibilityHttpIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
@AutoConfigureMockMvc
class EligibilityHttpIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-09-23T08:00:00Z");

    private static final String CUSTOMER_ID = "t025-customer";
    private static final String OTHER_CUSTOMER_ID = "t025-other";
    private static final String APPROVER_ID = "t025-approver";
    private static final String OWN_ORDER_ID = "t025-order-own";
    private static final String OTHER_ORDER_ID = "t025-order-other";
    private static final String RULE_CODE = "T025-STALLED";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

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
    void unauthenticatedEligibilityEvaluationIsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OWN_ORDER_ID, "LOGISTICS_DELAY")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedNonCustomerCannotUseCustomerEligibilityApi() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OWN_ORDER_ID, "LOGISTICS_DELAY")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void eligibleOwnedOrderReturnsAuthoritativeDecisionAndIgnoresDescriptiveReason() throws Exception {
        seedEligibleOwnedOrder(72);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OWN_ORDER_ID, "UNTRUSTED_MODEL_REASON")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.eligible").value(true))
                .andExpect(jsonPath("$.allowedAction").value("REFUND_ONLY"))
                .andExpect(jsonPath("$.maxRefundAmount").value(199.00))
                .andExpect(jsonPath("$.approvalRequired").value(false))
                .andExpect(jsonPath("$.ruleCode").value(RULE_CODE))
                .andExpect(jsonPath("$.ruleVersion").value(1))
                .andExpect(jsonPath("$.reasonCodes[0]").value("STALL_THRESHOLD_MET"))
                .andExpect(jsonPath("$.evaluatedAt").value("2026-09-23T08:00:00Z"));
    }

    @Test
    void knownFortySevenHourStallIsDeniedRatherThanManualReview() throws Exception {
        seedEligibleOwnedOrder(47);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OWN_ORDER_ID, "LOGISTICS_DELAY")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.eligible").value(false))
                .andExpect(jsonPath("$.allowedAction").value("DENY"))
                .andExpect(jsonPath("$.maxRefundAmount").value((Object) null))
                .andExpect(jsonPath("$.approvalRequired").value(false))
                .andExpect(jsonPath("$.reasonCodes[0]").value("STALL_THRESHOLD_NOT_MET"));
    }

    @Test
    void unknownStallDurationReturnsManualReviewInsteadOfAFalseDenial() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID);
        seedRule();
        Shipment shipment =
                Shipment.create("t025-shipment-unknown", OWN_ORDER_ID, "T025", "T025-UNKNOWN", ShipmentStatus.CREATED);
        shipmentRepository.saveAndFlush(shipment);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OWN_ORDER_ID, "LOGISTICS_DELAY")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.eligible").value(false))
                .andExpect(jsonPath("$.allowedAction").value("MANUAL_REVIEW"))
                .andExpect(jsonPath("$.reasonCodes[0]").value("LOGISTICS_EVIDENCE_UNAVAILABLE"));
    }

    @Test
    void anotherCustomersOrderAndMissingOrderAreConcealedTheSameWay() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedUser(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID);
        seedRule();
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        String message = "The order does not exist or is not accessible to the authenticated user";

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody(OTHER_ORDER_ID, "LOGISTICS_DELAY")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody("t025-order-missing", "LOGISTICS_DELAY")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));
    }

    @Test
    void malformedDescriptiveReasonIsRejectedBeforeBusinessEvaluation() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"orderId\":\"" + OWN_ORDER_ID + "\",\"reasonCode\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));
    }

    @AfterEach
    void removeT025Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't025-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't025-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't025-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't025-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't025-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code LIKE 'T025-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't025-%'");
    }

    private void seedEligibleOwnedOrder(long stalledHours) {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID);
        seedRule();
        Shipment shipment = Shipment.create(
                "t025-shipment-own", OWN_ORDER_ID, "T025", "T025-OWN", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(Duration.ofHours(stalledHours)));
        shipmentRepository.saveAndFlush(shipment);
    }

    private void seedUser(String userId, UserRole role) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.saveAndFlush(User.create(userId, userId, role));
        }
    }

    private void seedOrder(String orderId, String ownerId) {
        Order order = Order.create(orderId, ownerId, OrderStatus.SHIPPED, new BigDecimal("199.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item",
                orderId + "-product",
                "T025 Headphones",
                "ELECTRONICS",
                new BigDecimal("199.00"),
                1));
        orderRepository.saveAndFlush(order);
    }

    private void seedRule() {
        if (ruleRepository.findByRuleCodeAndVersion(RULE_CODE, 1).isPresent()) {
            return;
        }
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                RULE_CODE,
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                7,
                new BigDecimal("500.00"),
                new BigDecimal("300.00"),
                AllowedAction.REFUND_ONLY,
                true,
                NOW.minus(Duration.ofDays(30)),
                null));
    }

    private static String requestBody(String orderId, String reasonCode) {
        return "{\"orderId\":\"" + orderId + "\",\"reasonCode\":\"" + reasonCode + "\"}";
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
