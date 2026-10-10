package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * T058 executable contract for SupportTicket creation, ownership, and audit.
 *
 * <p>Enabled in T060 after the production table and API were implemented. The HTTP boundary,
 * PostgreSQL business rows, and committed audit facts are checked together.
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SupportTicketHttpIntegrationTest {

    private static final String CUSTOMER_ID = "t058-customer";
    private static final String OTHER_CUSTOMER_ID = "t058-other";
    private static final String APPROVER_ID = "t058-approver";
    private static final String OWN_ORDER_ID = "t058-order-own";
    private static final String OTHER_ORDER_ID = "t058-order-other";
    private static final String RUN_ID = "58585858-1111-4222-8333-444444444444";

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
    void customerCanCreateOpenTicketForOwnedOrderWithStructuredEvidence() throws Exception {
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        MvcResult created = mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(OWN_ORDER_ID)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("OPEN"))
                .andExpect(jsonPath("$.ticketId").isNotEmpty())
                .andReturn();

        String ticketId =
                com.jayway.jsonpath.JsonPath.read(created.getResponse().getContentAsString(), "$.ticketId");
        Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT user_id, order_id, category, reason_code, evidence_summary, status, run_id
                  FROM commerce.support_tickets
                 WHERE id = ?
                """, ticketId);

        assertEquals(CUSTOMER_ID, row.get("user_id"));
        assertEquals(OWN_ORDER_ID, row.get("order_id"));
        assertEquals("AFTER_SALES_ESCALATION", row.get("category"));
        assertEquals("MANUAL_REVIEW_REQUIRED", row.get("reason_code"));
        assertEquals("LOGISTICS status=IN_TRANSIT; stalledHours=unknown", row.get("evidence_summary"));
        assertEquals("OPEN", row.get("status"));
        assertEquals(RUN_ID, row.get("run_id").toString());
    }

    @Test
    void crossOwnerAndMissingOrderAreConcealedAndCreateNothing() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        String message = "The order does not exist or is not accessible to the authenticated user";

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(OTHER_ORDER_ID)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody("t058-order-missing")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.message").value(message));

        Long tickets = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.support_tickets WHERE user_id = ?", Long.class, CUSTOMER_ID);
        assertEquals(0L, tickets);
    }

    @Test
    void successfulTicketCreateWritesBusinessAuditInTheSameCommittedWorld() throws Exception {
        seedOrder(OWN_ORDER_ID, CUSTOMER_ID);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        MvcResult created = mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(OWN_ORDER_ID)))
                .andExpect(status().isCreated())
                .andReturn();

        String ticketId =
                com.jayway.jsonpath.JsonPath.read(created.getResponse().getContentAsString(), "$.ticketId");

        Map<String, Object> audit = jdbcTemplate.queryForMap("""
                SELECT actor_id, action, resource_type, resource_id, run_id, result,
                       metadata_json ->> 'category' AS category,
                       metadata_json ->> 'reasonCode' AS reason_code
                  FROM commerce.audit_logs
                 WHERE action = 'SUPPORT_TICKET_CREATED'
                   AND resource_id = ?
                """, ticketId);

        assertEquals(CUSTOMER_ID, audit.get("actor_id"));
        assertEquals("SUPPORT_TICKET_CREATED", audit.get("action"));
        assertEquals("SUPPORT_TICKET", audit.get("resource_type"));
        assertEquals(ticketId, audit.get("resource_id"));
        assertEquals(RUN_ID, audit.get("run_id").toString());
        assertEquals("SUCCESS", audit.get("result"));
        assertEquals("AFTER_SALES_ESCALATION", audit.get("category"));
        assertEquals("MANUAL_REVIEW_REQUIRED", audit.get("reason_code"));
    }

    @Test
    void nonCustomerRoleCannotUseCustomerEscalationCapability() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(null)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void unresolvedOrderStillAllowsSafeEscalation() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(null)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("OPEN"));

        Long tickets = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.support_tickets WHERE user_id = ? AND order_id IS NULL",
                Long.class,
                CUSTOMER_ID);
        assertEquals(1L, tickets);
    }

    @Test
    void blankReasonCodeCannotCreateTicket() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(null).replace("MANUAL_REVIEW_REQUIRED", "")))
                .andExpect(status().isBadRequest());

        Long tickets = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.support_tickets WHERE user_id = ?", Long.class, CUSTOMER_ID);
        assertEquals(0L, tickets);
    }

    @Test
    void rawBearerEvidenceIsRejectedWithoutPersistingTicket() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/support-tickets")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketBody(null)
                                .replace(
                                        "LOGISTICS status=IN_TRANSIT; stalledHours=unknown",
                                        "Bearer raw-secret-value")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        Long tickets = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.support_tickets WHERE user_id = ?", Long.class, CUSTOMER_ID);
        assertEquals(0L, tickets);
    }

    @AfterEach
    void removeT058Rows() {
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id LIKE 't058-%' OR actor_id LIKE 't058-%'");
        jdbcTemplate.update("DELETE FROM commerce.support_tickets WHERE user_id LIKE 't058-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't058-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't058-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't058-%'");
    }

    private void seedOrder(String orderId, String ownerId) {
        seedUser(ownerId, UserRole.CUSTOMER);
        Order order = Order.create(orderId, ownerId, OrderStatus.SHIPPED, new BigDecimal("199.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item",
                orderId + "-product",
                "T058 Escalation Item",
                "T058_CATEGORY",
                new BigDecimal("199.00"),
                1));
        orderRepository.saveAndFlush(order);
    }

    private void seedUser(String userId, UserRole role) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.saveAndFlush(User.create(userId, userId, role));
        }
    }

    private static String ticketBody(String orderId) {
        String orderField = orderId == null ? "null" : "\"" + orderId + "\"";
        return "{"
                + "\"orderId\":"
                + orderField
                + ",\"category\":\"AFTER_SALES_ESCALATION\""
                + ",\"reasonCode\":\"MANUAL_REVIEW_REQUIRED\""
                + ",\"evidenceSummary\":\"LOGISTICS status=IN_TRANSIT; stalledHours=unknown\""
                + ",\"runId\":\""
                + RUN_ID
                + "\"}";
    }
}
