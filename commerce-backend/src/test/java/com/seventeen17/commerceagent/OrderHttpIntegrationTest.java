package com.seventeen17.commerceagent;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * T023: prove the real HTTP boundary preserves authentication, capability and ownership semantics.
 *
 * <p>T019 already tests {@code OrderService} directly. These cases start at MockMvc so a green test
 * proves the whole path: Bearer JWT -> Spring Security -> OrderController -> OrderService ->
 * PostgreSQL -> JSON/error envelope.
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class OrderHttpIntegrationTest {

    private static final String CUSTOMER_ID = "t023-customer";
    private static final String OTHER_CUSTOMER_ID = "t023-other";
    private static final String APPROVER_ID = "t023-approver";
    private static final String OWN_ORDER_ID = "t023-order-own";
    private static final String OTHER_ORDER_ID = "t023-order-other";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void unauthenticatedOrderListIsRejected() throws Exception {
        mockMvc.perform(get("/api/v1/orders")).andExpect(status().isUnauthorized());
    }

    @Test
    void unauthenticatedOrderDetailIsRejected() throws Exception {
        mockMvc.perform(get("/api/v1/orders/{orderId}", OWN_ORDER_ID)).andExpect(status().isUnauthorized());
    }

    @Test
    void customerOrderListContainsOnlyOwnedOrders() throws Exception {
        seedCustomerOrders();
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].orderId").value(OWN_ORDER_ID))
                .andExpect(jsonPath("$[0].productSummary").value("T023 Headphones"))
                .andExpect(jsonPath("$[0].status").value("SHIPPED"));
    }

    @Test
    void customerCanReadAnOwnedOrderSnapshot() throws Exception {
        seedCustomerOrders();
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}", OWN_ORDER_ID).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value(OWN_ORDER_ID))
                .andExpect(jsonPath("$.status").value("SHIPPED"))
                .andExpect(jsonPath("$.currency").value("USD"))
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].productName").value("T023 Headphones"));
    }

    @Test
    void anotherCustomersOrderAndAMissingOrderAreConcealedTheSameWay() throws Exception {
        seedCustomerOrders();
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        String message = "The order does not exist or is not accessible to the authenticated user";

        mockMvc.perform(get("/api/v1/orders/{orderId}", OTHER_ORDER_ID).header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        mockMvc.perform(get("/api/v1/orders/{orderId}", "t023-order-missing")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));
    }

    @Test
    void authenticatedNonCustomerCannotUseCustomerOrderApi() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(get("/api/v1/orders").header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void authenticatedNonCustomerCannotUseCustomerOrderDetailApi() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(get("/api/v1/orders/{orderId}", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @AfterEach
    void removeT023Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't023-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't023-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't023-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't023-%'");
    }

    private void seedCustomerOrders() {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedUser(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID, "T023 Headphones");
        seedOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID, "T023 Other Product");
    }

    private void seedUser(String userId, UserRole role) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.saveAndFlush(User.create(userId, userId, role));
        }
    }

    private void seedOrder(String orderId, String ownerId, String productName) {
        Order order = Order.create(orderId, ownerId, OrderStatus.SHIPPED, new BigDecimal("199.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item", orderId + "-product", productName, "ELECTRONICS", new BigDecimal("199.00"), 1));
        orderRepository.saveAndFlush(order);
    }
}
