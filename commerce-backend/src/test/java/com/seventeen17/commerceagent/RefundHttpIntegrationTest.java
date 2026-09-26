package com.seventeen17.commerceagent;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * T028 executable HTTP contract for refund create + authoritative after-sales verification.
 *
 * <p>These tests deliberately start above the controller: Bearer JWT -> Spring Security ->
 * RefundController -> RefundService -> PostgreSQL. T021 already proves the service's concurrency
 * semantics; this class proves the same safety properties survive the HTTP boundary.
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, RefundHttpIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
@AutoConfigureMockMvc
class RefundHttpIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-09-26T08:00:00Z");
    private static final String CUSTOMER_ID = "t028-customer";
    private static final String OTHER_CUSTOMER_ID = "t028-other";
    private static final String APPROVER_ID = "t028-approver";
    private static final String OWN_ORDER_ID = "t028-order-own";
    private static final String OTHER_ORDER_ID = "t028-order-other";
    private static final String RULE_CODE = "T028-STALLED";
    private static final String RUN_ID = "11111111-2222-4333-8444-555555555555";
    private static final String KEY = "t028_key_primary";

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
    void unauthenticatedRefundCreateIsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/refunds")
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, RUN_ID)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedNonCustomerCannotUseRefundApi() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, RUN_ID)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void ownedRefundCreateAndSameKeyReplayReturnTheSameAuthoritativeRefund() throws Exception {
        seedRefundableOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        MvcResult first = mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, RUN_ID)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CREATED"))
                .andExpect(jsonPath("$.acceptedAmount").value(199.00))
                .andReturn();

        String refundId = com.jayway.jsonpath.JsonPath.read(first.getResponse().getContentAsString(), "$.refundRequestId");

        mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, UUID.randomUUID().toString())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.refundRequestId").value(refundId));

        Long rows = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.refund_requests WHERE order_id = ?", Long.class, OWN_ORDER_ID);
        org.junit.jupiter.api.Assertions.assertEquals(1L, rows);
    }

    @Test
    void sameOrderWithDifferentKeyIsRejectedAsDuplicateAfterSales() throws Exception {
        seedRefundableOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        createRefund(token, KEY, OWN_ORDER_ID);

        mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "t028_key_second")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, UUID.randomUUID().toString())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("DUPLICATE_AFTER_SALES"));
    }

    @Test
    void sameKeyWithDifferentPayloadIsRejectedAsIdempotencyConflict() throws Exception {
        seedRefundableOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        createRefund(token, KEY, OWN_ORDER_ID);

        mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, RUN_ID).replace("LOGISTICS_DELAY", "DIFFERENT_REASON")))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("IDEMPOTENCY_CONFLICT"));
    }

    @Test
    void recoveryReadFiltersByTheExactLogicalKeyAndUsesExplicitEmptyLists() throws Exception {
        seedRefundableOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        MvcResult created = createRefund(token, KEY, OWN_ORDER_ID);
        String refundId =
                com.jayway.jsonpath.JsonPath.read(created.getResponse().getContentAsString(), "$.refundRequestId");

        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token)
                        .queryParam("idempotencyKey", KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.refunds.length()").value(1))
                .andExpect(jsonPath("$.refunds[0].refundRequestId").value(refundId))
                .andExpect(jsonPath("$.returns.length()").value(0));

        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token)
                        .queryParam("idempotencyKey", "t028_key_absent"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.refunds.length()").value(0))
                .andExpect(jsonPath("$.returns.length()").value(0));
    }

    @Test
    void crossOwnerAndMissingOrderAreConcealedTheSameWayOnRecoveryRead() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedUser(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        String message = "The order does not exist or is not accessible to the authenticated user";

        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OTHER_ORDER_ID)
                        .header("Authorization", "Bearer " + token)
                        .queryParam("idempotencyKey", KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", "t028-order-missing")
                        .header("Authorization", "Bearer " + token)
                        .queryParam("idempotencyKey", KEY))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));
    }

    @Test
    void malformedIdempotencyKeysAreRejectedBeforeMoneyOrRecoveryReadsProceed() throws Exception {
        seedRefundableOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "bad.key")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(OWN_ORDER_ID, RUN_ID)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token)
                        .queryParam("idempotencyKey", "bad.key"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));
    }

    private MvcResult createRefund(String token, String key, String orderId) throws Exception {
        return mockMvc.perform(post("/api/v1/refunds")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(refundBody(orderId, RUN_ID)))
                .andExpect(status().isOk())
                .andReturn();
    }

    @AfterEach
    void removeT028Rows() {
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id IN "
                        + "(SELECT id FROM commerce.refund_requests WHERE order_id LIKE 't028-%') "
                        + "OR resource_id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.refund_requests WHERE order_id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't028-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code = ?", RULE_CODE);
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't028-%'");
    }

    private void seedRefundableOrder(String orderId, String ownerId) {
        seedUser(ownerId, UserRole.CUSTOMER);
        seedOrder(orderId, ownerId);
        seedRule();
        Shipment shipment =
                Shipment.create(orderId + "-shipment", orderId, "T028", orderId + "-tracking", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(Duration.ofHours(72)));
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
                "T028 Headphones",
                "T028_ELECTRONICS",
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
                "T028_ELECTRONICS",
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

    private static String refundBody(String orderId, String runId) {
        return "{\"orderId\":\""
                + orderId
                + "\",\"reasonCode\":\"LOGISTICS_DELAY\",\"requestedAmount\":199.00,"
                + "\"approvalRequestId\":null,\"runId\":\""
                + runId
                + "\"}";
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
