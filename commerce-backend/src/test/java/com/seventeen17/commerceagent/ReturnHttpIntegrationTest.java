package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
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
import java.sql.Timestamp;
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
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * T040 executable HTTP contract for return create + the authoritative after-sales read.
 *
 * <p>These tests deliberately start above the controller: Bearer JWT -> Spring Security ->
 * ReturnController -> ReturnService -> PostgreSQL. The point is not to re-prove the service's rules but to
 * show the same safety properties survive the HTTP boundary: ownership concealment, idempotent replay,
 * duplicate refusal, fail-closed approval references, and — the US2-specific one — that a delivered order
 * can never buy a direct refund through this endpoint either.
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, ReturnHttpIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
@AutoConfigureMockMvc
class ReturnHttpIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-10-06T08:00:00Z");
    private static final String CUSTOMER_ID = "t040-customer";
    private static final String OTHER_CUSTOMER_ID = "t040-other";
    private static final String APPROVER_ID = "t040-approver";
    private static final String OWN_ORDER_ID = "t040-order-own";
    private static final String OTHER_ORDER_ID = "t040-order-other";
    private static final String MISSING_ORDER_ID = "t040-order-missing";
    private static final String RUN_ID = "22222222-3333-4444-8555-666666666666";
    private static final String KEY = "t040_key_primary";
    private static final int WINDOW_DAYS = 7;

    /** 每个用例用自己的类目：规则选择把"两个不同 ruleCode 同时匹配"判成冲突，共用类目会让用例互相污染。 */
    private static final String HAPPY_CATEGORY = "T040_HAPPY";

    private static final String REFUND_ONLY_CATEGORY = "T040_REFUND_ONLY";
    private static final String EXPIRED_CATEGORY = "T040_EXPIRED";
    private static final String CONCEALMENT_CATEGORY = "T040_CONCEALMENT";

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
    void unauthenticatedReturnCreateIsRejected() throws Exception {
        mockMvc.perform(post("/api/v1/returns")
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, null)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("AUTH_REQUIRED"));
    }

    @Test
    void authenticatedNonCustomerCannotCreateAReturn() throws Exception {
        seedUser(APPROVER_ID, UserRole.APPROVER);
        String token = localJwtIssuer.issue(APPROVER_ID);

        mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, null)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("ACCESS_DENIED"));
    }

    @Test
    void anotherUsersOrderIsIndistinguishableFromAMissingOrder() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedUser(OTHER_CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OTHER_ORDER_ID, OTHER_CUSTOMER_ID, CONCEALMENT_CATEGORY);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        MvcResult crossOwner = mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OTHER_ORDER_ID, null, null)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andReturn();

        MvcResult missing = mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(MISSING_ORDER_ID, null, null)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("ORDER_NOT_FOUND"))
                .andReturn();

        // 两条失败路径的消息必须逐字相同，否则状态码/文案差异本身就是"这个 orderId 真实存在"的预言机。
        String crossOwnerMessage = JsonPath.read(crossOwner.getResponse().getContentAsString(), "$.message");
        String missingMessage = JsonPath.read(missing.getResponse().getContentAsString(), "$.message");
        assertEquals(crossOwnerMessage, missingMessage);
    }

    @Test
    void aReturnInsideTheWindowIsCreatedWithAFrozenDeadlineAndNoRefundRow() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, HAPPY_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(3));
        seedReturnRule("T040-HAPPY", HAPPY_CATEGORY, WINDOW_DAYS, AllowedAction.RETURN_REFUND);

        MvcResult result = createReturn(localJwtIssuer.issue(CUSTOMER_ID), KEY, OWN_ORDER_ID);

        String returnRequestId = JsonPath.read(result.getResponse().getContentAsString(), "$.returnRequestId");
        assertFalse(returnRequestId.isBlank(), "服务端必须返回真实存在的行 id，而不是回显请求");

        // 截止日 = 运单签收时刻 + 规则窗口：受理时就冻结。
        Instant expectedDeadline = NOW.minus(Duration.ofDays(3)).plus(Duration.ofDays(WINDOW_DAYS));
        assertEquals(
                expectedDeadline.toString(),
                JsonPath.read(result.getResponse().getContentAsString(), "$.returnDeadline"));
        assertEquals(
                expectedDeadline,
                jdbcTemplate
                        .queryForObject(
                                "SELECT return_deadline FROM commerce.return_requests WHERE id = ?",
                                Timestamp.class,
                                returnRequestId)
                        .toInstant());

        // 一行退货、订单投影改向、审计同事务落地。
        assertEquals(1, countReturnsFor(OWN_ORDER_ID));
        assertEquals(
                "RETURN_REQUESTED",
                jdbcTemplate.queryForObject(
                        "SELECT after_sales_status FROM commerce.orders WHERE id = ?", String.class, OWN_ORDER_ID));
        assertEquals(
                1,
                jdbcTemplate.queryForObject(
                        "SELECT count(*) FROM commerce.audit_logs WHERE action = 'RETURN_CREATED' AND resource_id = ?",
                        Integer.class,
                        returnRequestId));

        // 本次决定（只创建退货行）的可执行证据：RETURN_REFUND 也不会顺手写一笔退款。
        assertEquals(0, countRefundsFor(OWN_ORDER_ID));

        // 写后验证读的是同一个聚合，而且能按幂等键精确定位到"我这一笔"。
        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + localJwtIssuer.issue(CUSTOMER_ID))
                        .param("idempotencyKey", KEY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.returns[0].returnRequestId").value(returnRequestId))
                .andExpect(jsonPath("$.returns[0].status").value("CREATED"))
                .andExpect(jsonPath("$.refunds").isEmpty());

        // 换一把 key 读同一订单：聚合里必须没有它，否则"用 key 精确读回"就没有精度可言。
        mockMvc.perform(get("/api/v1/orders/{orderId}/after-sales", OWN_ORDER_ID)
                        .header("Authorization", "Bearer " + localJwtIssuer.issue(CUSTOMER_ID))
                        .param("idempotencyKey", "t040_key_absent"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.returns").isEmpty());
    }

    @Test
    void replayingTheSameKeyReturnsTheSameReturnWithoutASecondRow() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, HAPPY_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(3));
        seedReturnRule("T040-HAPPY", HAPPY_CATEGORY, WINDOW_DAYS, AllowedAction.RETURN_REFUND);
        String token = localJwtIssuer.issue(CUSTOMER_ID);

        String first = JsonPath.read(
                createReturn(token, KEY, OWN_ORDER_ID).getResponse().getContentAsString(), "$.returnRequestId");
        String replayed = JsonPath.read(
                createReturn(token, KEY, OWN_ORDER_ID).getResponse().getContentAsString(), "$.returnRequestId");

        assertEquals(first, replayed, "同一个 key 必须返回同一笔，而不是第二笔");
        assertEquals(1, countReturnsFor(OWN_ORDER_ID));
    }

    @Test
    void aSecondKeyForTheSameOrderIsADuplicate() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, HAPPY_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(3));
        seedReturnRule("T040-HAPPY", HAPPY_CATEGORY, WINDOW_DAYS, AllowedAction.RETURN_REFUND);
        String token = localJwtIssuer.issue(CUSTOMER_ID);
        createReturn(token, KEY, OWN_ORDER_ID);

        mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", "t040_key_second")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, null)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("DUPLICATE_AFTER_SALES"));

        assertEquals(1, countReturnsFor(OWN_ORDER_ID));
    }

    @Test
    void anApprovalReferenceIsRefusedInThisVersion() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, HAPPY_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(3));
        seedReturnRule("T040-HAPPY", HAPPY_CATEGORY, WINDOW_DAYS, AllowedAction.RETURN_REFUND);

        mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + localJwtIssuer.issue(CUSTOMER_ID))
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, "approval-that-cannot-be-verified")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"));

        // 被拒绝的请求不得留下任何业务痕迹：宁可拒绝，也不留一条"看起来已获批准"的记录。
        assertEquals(0, countReturnsFor(OWN_ORDER_ID));
    }

    @Test
    void aDeliveredOrderWithARefundOnlyRuleIsDeniedInsteadOfRefunded() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, REFUND_ONLY_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(3));
        seedReturnRule("T040-REFUND-ONLY", REFUND_ONLY_CATEGORY, null, AllowedAction.REFUND_ONLY);

        mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + localJwtIssuer.issue(CUSTOMER_ID))
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, null)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.errorCode").value("ELIGIBILITY_DENIED"));

        assertEquals(0, countReturnsFor(OWN_ORDER_ID));
        assertEquals(0, countRefundsFor(OWN_ORDER_ID));
    }

    @Test
    void aReturnPastItsWindowIsDenied() throws Exception {
        seedUser(CUSTOMER_ID, UserRole.CUSTOMER);
        seedDeliveredOrder(OWN_ORDER_ID, CUSTOMER_ID, EXPIRED_CATEGORY);
        seedSignedShipment(OWN_ORDER_ID, Duration.ofDays(30));
        seedReturnRule("T040-EXPIRED", EXPIRED_CATEGORY, WINDOW_DAYS, AllowedAction.RETURN);

        mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + localJwtIssuer.issue(CUSTOMER_ID))
                        .header("Idempotency-Key", KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(OWN_ORDER_ID, null, null)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.errorCode").value("ELIGIBILITY_DENIED"));

        assertEquals(0, countReturnsFor(OWN_ORDER_ID));
    }

    private MvcResult createReturn(String token, String key, String orderId) throws Exception {
        return mockMvc.perform(post("/api/v1/returns")
                        .header("Authorization", "Bearer " + token)
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(returnBody(orderId, null, null)))
                .andExpect(status().isOk())
                .andReturn();
    }

    private int countReturnsFor(String orderId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM commerce.return_requests WHERE order_id = ?", Integer.class, orderId);
        return count == null ? 0 : count;
    }

    private int countRefundsFor(String orderId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM commerce.refund_requests WHERE order_id = ?", Integer.class, orderId);
        return count == null ? 0 : count;
    }

    private void seedUser(String userId, UserRole role) {
        if (userRepository.findById(userId).isEmpty()) {
            userRepository.saveAndFlush(User.create(userId, userId, role));
        }
    }

    private void seedDeliveredOrder(String orderId, String ownerId, String category) {
        Order order = Order.create(orderId, ownerId, OrderStatus.DELIVERED, new BigDecimal("120.00"), "USD");
        order.addItem(OrderItem.create(
                orderId + "-item", orderId + "-product", "T040 Product", category, new BigDecimal("120.00"), 1));
        orderRepository.saveAndFlush(order);
    }

    private void seedSignedShipment(String orderId, Duration signedFor) {
        Shipment shipment = Shipment.create(
                orderId + "-shipment", orderId, "T040", orderId + "-tracking", ShipmentStatus.DELIVERED);
        shipment.setSignedAt(NOW.minus(signedFor));
        shipmentRepository.saveAndFlush(shipment);
    }

    private void seedReturnRule(String ruleCode, String category, Integer windowDays, AllowedAction action) {
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                ruleCode,
                1,
                category,
                OrderStatus.DELIVERED,
                // 退货规则不得声明停滞阈值：已签收运单会让停滞分支命中冲突检查并转人工。
                null,
                windowDays,
                new BigDecimal("500.00"),
                new BigDecimal("1000.00"),
                action,
                true,
                NOW.minus(Duration.ofDays(30)),
                null));
    }

    private static String returnBody(String orderId, String returnMethod, String approvalRequestId) {
        return "{\"orderId\":\""
                + orderId
                + "\",\"reasonCode\":\"DELIVERED_RETURN\",\"returnMethod\":"
                + (returnMethod == null ? "null" : "\"" + returnMethod + "\"")
                + ",\"approvalRequestId\":"
                + (approvalRequestId == null ? "null" : "\"" + approvalRequestId + "\"")
                + ",\"runId\":\""
                + RUN_ID
                + "\"}";
    }

    @AfterEach
    void removeT040Rows() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs WHERE resource_type = 'RETURN' AND resource_id IN "
                + "(SELECT id FROM commerce.return_requests WHERE order_id LIKE 't040-%')");
        jdbcTemplate.update("DELETE FROM commerce.return_requests WHERE order_id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.refund_requests WHERE order_id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't040-%'");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code LIKE 'T040-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't040-%'");
        assertTrue(jdbcTemplate.queryForObject(
                        "SELECT count(*) FROM commerce.return_requests WHERE order_id LIKE 't040-%'", Integer.class)
                == 0);
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
