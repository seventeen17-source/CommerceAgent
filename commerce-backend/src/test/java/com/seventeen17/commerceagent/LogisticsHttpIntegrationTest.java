package com.seventeen17.commerceagent;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.logistics.LogisticsEvent;
import com.seventeen17.commerceagent.logistics.LogisticsEventRepository;
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
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * T024: prove the real logistics HTTP boundary preserves authentication, capability, ownership and
 * authoritative stall semantics.
 *
 * <p>T019 already proves {@code LogisticsService} and {@code LogisticsStallCalculator} directly.
 * These cases start at MockMvc so a green test proves the complete path: Bearer JWT -> Spring
 * Security -> LogisticsController -> LogisticsService -> repositories -> deterministic stall
 * calculation -> JSON/error envelope.
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, LogisticsHttpIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
@AutoConfigureMockMvc
class LogisticsHttpIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-09-23T08:00:00Z");

    private static final String CUSTOMER_ID = "t024-customer";
    private static final String OTHER_CUSTOMER_ID = "t024-other";
    private static final String APPROVER_ID = "t024-approver";
    private static final String OWN_ORDER_ID = "t024-order-own";
    private static final String OTHER_ORDER_ID = "t024-order-other";

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
    private LogisticsEventRepository logisticsEventRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void unauthenticatedLogisticsReadIsRejected() throws Exception {
        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)).andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedNonCustomerCannotUseCustomerLogisticsApi() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void customerReceivesAuthoritativeStallSnapshotForOwnedOrder() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, OrderStatus.SHIPPED);
        Shipment shipment = seedShipment(
                "t024-shipment-own", OWN_ORDER_ID, ShipmentStatus.IN_TRANSIT, NOW.minus(Duration.ofHours(96)), null);
        logisticsEventRepository.saveAndFlush(LogisticsEvent.create(
                shipment, "IN_TRANSIT", "T024 more recent authoritative event", NOW.minus(Duration.ofHours(72))));

        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("IN_TRANSIT"))
                .andExpect(jsonPath("$.signed").value(false))
                .andExpect(jsonPath("$.lastMeaningfulEventAt").value("2026-09-20T08:00:00Z"))
                .andExpect(jsonPath("$.stalledHours").value(72));
    }

    @Test
    void missingEvidenceRemainsUnknownInsteadOfBecomingZeroHours() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, OrderStatus.SHIPPED);
        seedShipment("t024-shipment-no-evidence", OWN_ORDER_ID, ShipmentStatus.CREATED, null, null);

        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CREATED"))
                .andExpect(jsonPath("$.signed").value(false))
                .andExpect(jsonPath("$.lastMeaningfulEventAt").value((Object) null))
                .andExpect(jsonPath("$.stalledHours").value((Object) null));
    }

    @Test
    void anotherCustomersOrderAndMissingOrderAreConcealedTheSameWay() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedUser(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID, OrderStatus.SHIPPED);
        seedShipment(
                "t024-shipment-other",
                OTHER_ORDER_ID,
                ShipmentStatus.IN_TRANSIT,
                NOW.minus(Duration.ofHours(72)),
                null);

        String token = localJwtIssuer.issue(CUSTOMER_ID);
        String message = "The order does not exist or is not accessible to the authenticated user";

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OTHER_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", "t024-order-missing")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));
    }

    @Test
    void paidOrderWithoutShipmentIsBusinessStateNotRetryableDependencyFailure() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, OrderStatus.PAID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("INVALID_ORDER_STATE"))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    @Test
    void shippedOrderWithoutShipmentFailsClosedAsRetryableLogisticsUnavailable() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, OrderStatus.SHIPPED);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.errorCode").value("LOGISTICS_UNAVAILABLE"))
                .andExpect(jsonPath("$.retryable").value(true));
    }

    @Test
    void deliveredShipmentHasNoStallEvenWhenItsLastEventIsOld() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, OrderStatus.DELIVERED);
        seedShipment(
                "t024-shipment-delivered",
                OWN_ORDER_ID,
                ShipmentStatus.DELIVERED,
                NOW.minus(Duration.ofHours(120)),
                NOW.minus(Duration.ofHours(120)));
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}/logistics", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DELIVERED"))
                .andExpect(jsonPath("$.signed").value(true))
                .andExpect(jsonPath("$.stalledHours").value((Object) null));
    }

    @AfterEach
    void removeT024Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't024-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't024-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't024-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't024-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't024-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't024-%'");
    }

    private void seedUser(String userId, UserRole role) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.saveAndFlush(User.create(userId, userId, role));
        }
    }

    private void seedOrder(String orderId, String ownerId, OrderStatus status) {
        Order order = Order.create(orderId, ownerId, status, new BigDecimal("199.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item",
                orderId + "-product",
                "T024 Product",
                "ELECTRONICS",
                new BigDecimal("199.00"),
                1));
        orderRepository.saveAndFlush(order);
    }

    private Shipment seedShipment(
            String shipmentId, String orderId, ShipmentStatus status, Instant lastEventAt, Instant signedAt) {
        Shipment shipment = Shipment.create(shipmentId, orderId, "T024", "T024-" + shipmentId, status);
        shipment.setLastEventAt(lastEventAt);
        shipment.setSignedAt(signedAt);
        return shipmentRepository.saveAndFlush(shipment);
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
