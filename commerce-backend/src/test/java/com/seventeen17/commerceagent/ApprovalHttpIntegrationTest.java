package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.approval.ApprovalRequestRepository;
import com.seventeen17.commerceagent.audit.AuditLogRepository;
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
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * T052 executable HTTP contract for authoritative human approvals.
 *
 * <p>These tests start at Bearer JWT and end in PostgreSQL. T049 already proves the pure state
 * machine; this class proves the HTTP boundary cannot bypass role checks, deterministic eligibility,
 * exact binding, terminality, or structured audit.
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, ApprovalHttpIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
@AutoConfigureMockMvc
class ApprovalHttpIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-10-08T08:00:00Z");
    private static final String CUSTOMER_ID = "t052-customer";
    private static final String OTHER_CUSTOMER_ID = "t052-other";
    private static final String APPROVER_ID = "t052-approver";
    private static final String ORDER_ID = "t052-order";
    private static final String OTHER_ORDER_ID = "t052-order-other";
    private static final String RULE_CODE = "T052-HIGH-RISK";
    private static final String RUN_ID = "52000000-0000-4000-8000-000000000001";

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
    private ApprovalRequestRepository approvalRepository;

    @Autowired
    private AuditLogRepository auditRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @AfterEach
    void cleanUp() {
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_id IN "
                        + "(SELECT id FROM commerce.approval_requests WHERE order_id IN (?, ?))",
                ORDER_ID,
                OTHER_ORDER_ID);
        approvalRepository.deleteAll(
                approvalRepository.findAll().stream()
                        .filter(row -> row.getOrderId().equals(ORDER_ID) || row.getOrderId().equals(OTHER_ORDER_ID))
                        .toList());
        shipmentRepository.deleteAll(
                shipmentRepository.findAll().stream()
                        .filter(row -> row.getOrderId().equals(ORDER_ID) || row.getOrderId().equals(OTHER_ORDER_ID))
                        .toList());
        orderRepository.deleteById(ORDER_ID);
        orderRepository.deleteById(OTHER_ORDER_ID);
        ruleRepository
                .findByRuleCodeAndVersion(RULE_CODE, 1)
                .ifPresent(ruleRepository::delete);
        userRepository.deleteById(CUSTOMER_ID);
        userRepository.deleteById(OTHER_CUSTOMER_ID);
        userRepository.deleteById(APPROVER_ID);
    }

    @Test
    void customerCreatesPendingApprovalFromAuthoritativeEligibility() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String token = token(CUSTOMER_ID);

        MvcResult created = mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "REFUND_ONLY", "399.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").value(RUN_ID))
                .andExpect(jsonPath("$.orderId").value(ORDER_ID))
                .andExpect(jsonPath("$.actionType").value("REFUND_ONLY"))
                .andExpect(jsonPath("$.amount").value(399.00))
                .andExpect(jsonPath("$.riskReason").value("APPROVAL_REQUIRED_BY_AMOUNT"))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.decidedBy").doesNotExist())
                .andReturn();

        String approvalId =
                com.jayway.jsonpath.JsonPath.read(created.getResponse().getContentAsString(), "$.approvalRequestId");
        assertNotNull(approvalRepository.findById(approvalId).orElseThrow().getExpiresAt());
        assertEquals(
                1,
                auditRepository
                        .findByActionAndResourceIdOrderByCreatedAtAsc("APPROVAL_REQUESTED", approvalId)
                        .size());
    }

    @Test
    void createFailsClosedWhenCallerChangesActionAmountOrRiskReason() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String token = token(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "RETURN_REFUND", "399.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "REFUND_ONLY", "398.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "REFUND_ONLY", "399.00", "SOME_OTHER_REASON")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        assertEquals(0, countTestApprovals());
    }

    @Test
    void approverCannotUseTheCustomerApprovalCreateCapability() throws Exception {
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + approverToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "REFUND_ONLY", "399.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void crossOwnerApprovalCreateIsConcealedLikeMissingOrder() throws Exception {
        seedHighRiskOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID);
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        String token = token(CUSTOMER_ID);

        mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(OTHER_ORDER_ID, "REFUND_ONLY", "399.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"));

        assertEquals(0, approvalRepository.count());
    }

    @Test
    void ownerCanRereadExactApprovalButAnotherCustomerCannot() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String ownerToken = token(CUSTOMER_ID);
        String approvalId = createApproval(ownerToken);
        String otherToken = tokenWithRole(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);

        mockMvc.perform(get("/api/v1/approvals/{approvalId}", approvalId)
                        .header("Authorization", "Bearer " + ownerToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.approvalRequestId").value(approvalId))
                .andExpect(jsonPath("$.runId").value(RUN_ID))
                .andExpect(jsonPath("$.orderId").value(ORDER_ID))
                .andExpect(jsonPath("$.actionType").value("REFUND_ONLY"))
                .andExpect(jsonPath("$.amount").value(399.00))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.requestedAt").exists())
                .andExpect(jsonPath("$.expiresAt").exists());

        mockMvc.perform(get("/api/v1/approvals/{approvalId}", approvalId)
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("APPROVAL_NOT_FOUND"));
    }

    @Test
    void onlyApproverCanListTheWorklist() throws Exception {
        String customerToken = tokenWithRole(CUSTOMER_ID, UserRole.CUSTOMER);
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        mockMvc.perform(get("/api/v1/approvals")
                        .header("Authorization", "Bearer " + customerToken))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));

        mockMvc.perform(get("/api/v1/approvals")
                        .header("Authorization", "Bearer " + approverToken)
                        .queryParam("status", "PENDING"))
                .andExpect(status().isOk());
    }

    @Test
    void approverCanApproveAndDecisionIsAudited() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String customerToken = token(CUSTOMER_ID);
        String approvalId = createApproval(customerToken);
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        mockMvc.perform(post("/api/v1/approvals/{approvalId}/decision", approvalId)
                        .header("Authorization", "Bearer " + approverToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"APPROVE\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"))
                .andExpect(jsonPath("$.decidedBy").value(APPROVER_ID))
                .andExpect(jsonPath("$.decidedAt").exists());

        assertEquals(
                1,
                auditRepository
                        .findByActionAndResourceIdOrderByCreatedAtAsc("APPROVAL_DECIDED", approvalId)
                        .size());
    }

    @Test
    void customerCannotDecideApproval() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String customerToken = token(CUSTOMER_ID);
        String approvalId = createApproval(customerToken);

        mockMvc.perform(post("/api/v1/approvals/{approvalId}/decision", approvalId)
                        .header("Authorization", "Bearer " + customerToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"APPROVE\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));

        assertEquals("PENDING", approvalRepository.findById(approvalId).orElseThrow().getStatus().name());
    }

    @Test
    void terminalDecisionCannotBeReplacedButExactDecisionMayBeReplayed() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String approvalId = createApproval(token(CUSTOMER_ID));
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        decide(approverToken, approvalId, "APPROVE")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));

        decide(approverToken, approvalId, "APPROVE")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED"));

        decide(approverToken, approvalId, "DENY")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("APPROVAL_CONFLICT"));

        assertEquals("APPROVED", approvalRepository.findById(approvalId).orElseThrow().getStatus().name());
    }

    @Test
    void approverCanDenyAndTheDecisionIsAuthoritative() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String approvalId = createApproval(token(CUSTOMER_ID));
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        decide(approverToken, approvalId, "DENY")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DENIED"))
                .andExpect(jsonPath("$.decidedBy").value(APPROVER_ID));

        assertEquals("DENIED", approvalRepository.findById(approvalId).orElseThrow().getStatus().name());
    }

    @Test
    void expiredApprovalCannotBeDecidedAndExpiryIsPersisted() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String approvalId = createApproval(token(CUSTOMER_ID));
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        jdbcTemplate.update(
                "UPDATE commerce.approval_requests SET expires_at = ? WHERE id = ?",
                java.sql.Timestamp.from(NOW.minusSeconds(1)),
                approvalId);

        decide(approverToken, approvalId, "APPROVE")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("APPROVAL_EXPIRED"));

        assertEquals("EXPIRED", approvalRepository.findById(approvalId).orElseThrow().getStatus().name());
        assertEquals(
                1,
                auditRepository
                        .findByActionAndResourceIdOrderByCreatedAtAsc("APPROVAL_EXPIRED", approvalId)
                        .size());
    }

    @Test
    void replayingTheSameLiveProposalReturnsTheSameApproval() throws Exception {
        seedHighRiskOrder(ORDER_ID, CUSTOMER_ID);
        String token = token(CUSTOMER_ID);

        String first = createApproval(token);
        String second = createApproval(token);

        assertEquals(first, second);
        assertEquals(1, countTestApprovals());
    }

    @Test
    void unknownApprovalDecisionReturnsNotFoundInsteadOfInternalError() throws Exception {
        String approverToken = tokenWithRole(APPROVER_ID, UserRole.APPROVER);

        mockMvc.perform(post("/api/v1/approvals/{approvalId}/decision", "missing-approval")
                        .header("Authorization", "Bearer " + approverToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"decision\":\"DENY\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("APPROVAL_NOT_FOUND"));
    }

    private String createApproval(String customerToken) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/approvals")
                        .header("Authorization", "Bearer " + customerToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(ORDER_ID, "REFUND_ONLY", "399.00", "APPROVAL_REQUIRED_BY_AMOUNT")))
                .andExpect(status().isCreated())
                .andReturn();
        return com.jayway.jsonpath.JsonPath.read(
                result.getResponse().getContentAsString(), "$.approvalRequestId");
    }

    private org.springframework.test.web.servlet.ResultActions decide(
            String token, String approvalId, String decision) throws Exception {
        return mockMvc.perform(post("/api/v1/approvals/{approvalId}/decision", approvalId)
                .header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\":\"" + decision + "\"}"));
    }

    private String token(String userId) {
        seedUser(userId, UserRole.CUSTOMER);
        return localJwtIssuer.issue(userId);
    }

    private String tokenWithRole(String userId, UserRole role) {
        seedUser(userId, role);
        return localJwtIssuer.issue(userId);
    }

    private void seedHighRiskOrder(String orderId, String ownerId) {
        seedUser(ownerId, UserRole.CUSTOMER);
        Order order = Order.create(orderId, ownerId, OrderStatus.SHIPPED, new BigDecimal("399.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item",
                orderId + "-product",
                "T052 Headphones",
                "T052_ELECTRONICS",
                new BigDecimal("399.00"),
                1));
        orderRepository.saveAndFlush(order);

        Shipment shipment = Shipment.create(
                orderId + "-shipment", orderId, "T052", orderId + "-tracking", ShipmentStatus.IN_TRANSIT);
        shipment.setLastEventAt(NOW.minus(Duration.ofHours(72)));
        shipmentRepository.saveAndFlush(shipment);

        if (ruleRepository.findByRuleCodeAndVersion(RULE_CODE, 1).isEmpty()) {
            ruleRepository.saveAndFlush(AfterSalesRule.create(
                    RULE_CODE,
                    1,
                    "T052_ELECTRONICS",
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
    }

    private void seedUser(String userId, UserRole role) {
        userRepository.findById(userId).ifPresentOrElse(
                user -> {
                    user.setRole(role);
                    userRepository.saveAndFlush(user);
                },
                () -> userRepository.saveAndFlush(User.create(userId, userId, role)));
    }

    private int countTestApprovals() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM commerce.approval_requests WHERE order_id IN (?, ?)",
                Integer.class,
                ORDER_ID,
                OTHER_ORDER_ID);
        assertNotNull(count);
        return count;
    }

    private static String createBody(String orderId, String action, String amount, String riskReason) {
        return "{\"runId\":\""
                + RUN_ID
                + "\",\"orderId\":\""
                + orderId
                + "\",\"actionType\":\""
                + action
                + "\",\"amount\":"
                + amount
                + ",\"riskReason\":\""
                + riskReason
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
