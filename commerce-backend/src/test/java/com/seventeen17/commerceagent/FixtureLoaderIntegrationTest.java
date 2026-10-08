package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditLogRepository;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.fixture.FixtureLoader;
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class FixtureLoaderIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private FixtureLoader fixtureLoader;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private AuditWriter auditWriter;

    @Autowired
    private AuditLogRepository auditLogRepository;

    @Test
    void resetBuildsDeterministicCommerceStateAndClearsAudit() throws Exception {
        seedAuthenticatedUser();
        String token = localJwtIssuer.issue("customer-001");

        performReset(token);

        assertEquals(
                3,
                count(
                        "SELECT COUNT(*) FROM commerce.users WHERE id IN ('customer-001','customer-002','approver-001')"));
        assertEquals(2, count("SELECT COUNT(*) FROM commerce.orders WHERE id IN ('order-001','order-002')"));
        assertEquals(2, count("SELECT COUNT(*) FROM commerce.shipments WHERE id IN ('shipment-001','shipment-002')"));
        assertEquals(1, count("""
                        SELECT COUNT(*) FROM commerce.after_sales_rules
                        WHERE rule_code = 'LOGISTICS_STALLED_REFUND' AND version = 1
                        """));

        auditWriter.writeSecurityEvent(new AuditEvent(
                AuditActorType.SYSTEM,
                "commerce-backend",
                "TEST_AUDIT",
                "ORDER",
                "order-001",
                null,
                "DENIED",
                Map.of("traceId", "fixture-test")));
        assertNotEquals(0, auditLogRepository.count());

        // T051: approval is a run-produced business fact just like refund/return state. If reset does
        // not clear it, the next Eval run inherits a human decision from the previous world.
        jdbcTemplate.update("""
                INSERT INTO commerce.approval_requests
                    (id, run_id, order_id, user_id, action, amount, status,
                     eligibility_rule_code, reason_code, expires_at)
                VALUES
                    ('approval-fixture-001', 'run-fixture-001', 'order-001', 'customer-001',
                     'REFUND_ONLY', 199.00, 'PENDING',
                     'LOGISTICS_STALLED_REFUND', 'APPROVAL_REQUIRED_BY_AMOUNT',
                     now() + interval '1 hour')
                """);
        assertEquals(1, count("SELECT COUNT(*) FROM commerce.approval_requests"));

        jdbcTemplate.update("UPDATE commerce.orders SET status = 'CANCELLED' WHERE id = 'order-001'");
        performReset(token);

        assertEquals(0, count("SELECT COUNT(*) FROM commerce.approval_requests"));
        assertEquals(
                "SHIPPED",
                jdbcTemplate.queryForObject("SELECT status FROM commerce.orders WHERE id = 'order-001'", String.class));
        assertEquals(0, auditLogRepository.count());
        assertEquals("2026-09-12 08:00:00+00", jdbcTemplate.queryForObject("""
                        SELECT to_char(last_event_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS') || '+00'
                        FROM commerce.shipments WHERE id = 'shipment-001'
                        """, String.class));
    }

    @Test
    void unknownCaseUsesContractError() throws Exception {
        seedAuthenticatedUser();
        String token = localJwtIssuer.issue("customer-001");

        mockMvc.perform(post("/internal/eval/fixtures/unknown-case/reset")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"datasetVersion\":\"v1\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("EVAL_CASE_NOT_FOUND"))
                .andExpect(jsonPath("$.retryable").value(false));
    }

    @Test
    void concurrentResetUsesDatabaseLockAndReturnsConflict() throws Exception {
        seedAuthenticatedUser();
        String token = localJwtIssuer.issue("customer-001");

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement =
                    connection.prepareStatement("SELECT pg_advisory_xact_lock(CAST(hashtext(?) AS BIGINT))")) {
                statement.setString(1, "commerceagent-eval-fixture-reset");
                statement.execute();
            }

            mockMvc.perform(post("/internal/eval/fixtures/refund-logistics-001/reset")
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"datasetVersion\":\"v1\"}"))
                    .andExpect(status().isConflict())
                    .andExpect(jsonPath("$.errorCode").value("EVAL_RESET_CONFLICT"))
                    .andExpect(jsonPath("$.retryable").value(true));

            connection.rollback();
        }
    }

    @Test
    void endpointRequiresAuthentication() throws Exception {
        mockMvc.perform(post("/internal/eval/fixtures/refund-logistics-001/reset")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"datasetVersion\":\"v1\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("AUTH_REQUIRED"));
    }

    @Test
    void developmentSeedingAcquiresTheBlockingLockAndRunsUnderTheTestProfile() {
        // DevelopmentFixtureInitializer is @Profile("dev"), so `mvnw verify` never exercised this
        // path -- which is how a void-returning advisory lock mapped to Boolean survived T014 and
        // broke `spring-boot:run`. Calling the loader directly pins the behaviour for every profile.
        fixtureLoader.seedDevelopmentFixtures();

        assertEquals(
                3,
                count(
                        "SELECT COUNT(*) FROM commerce.users WHERE id IN ('customer-001','customer-002','approver-001')"));
        assertEquals(2, count("SELECT COUNT(*) FROM commerce.orders WHERE id IN ('order-001','order-002')"));
    }

    @Test
    void theAmbiguityCaseSeedsTwoWritableOrdersAndOnlyOneMatchingRule() throws Exception {
        seedAuthenticatedUser();
        String token = localJwtIssuer.issue("customer-001");

        mockMvc.perform(post("/internal/eval/fixtures/order-ambiguous-001/reset")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"datasetVersion\":\"v1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("order-ambiguous-001"))
                .andExpect(jsonPath("$.fixtureVersion").value("t048-order-ambiguous-001-v1"));

        // Two delivered orders described by the same clue. Two candidates is the whole point: with one
        // order there would be nothing to ask about, and the case would prove nothing.
        assertEquals(2, count("""
                        SELECT COUNT(*) FROM commerce.orders
                         WHERE id IN ('order-101','order-102') AND status = 'DELIVERED'
                        """));
        assertEquals(2, count("""
                        SELECT COUNT(*) FROM commerce.order_items
                         WHERE order_id IN ('order-101','order-102') AND product_name LIKE '%耳机%'
                        """));
        // Signed inside the window *relative to the reset* -- a literal timestamp is what rots.
        assertEquals(2, count("""
                        SELECT COUNT(*) FROM commerce.shipments
                         WHERE order_id IN ('order-101','order-102')
                           AND signed_at > now() - interval '7 days'
                        """));
        // Exactly one active rule may cover them. Two matching ruleCodes is a CONFLICTING_RULES refusal
        // by design, and that is what turned T042's second real run into a failure of the *fixture*.
        assertEquals(1, count("""
                        SELECT COUNT(*) FROM commerce.after_sales_rules
                         WHERE active = TRUE AND required_order_status = 'DELIVERED'
                           AND (product_category IS NULL OR product_category = 'APPAREL')
                        """));
    }

    @Test
    void theClueNarrowingCaseSeedsThreeWritableOrdersAndOnlyOneDescribedByTheClue() throws Exception {
        seedAuthenticatedUser();
        String token = localJwtIssuer.issue("customer-001");

        mockMvc.perform(post("/internal/eval/fixtures/order-clue-narrow-001/reset")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"datasetVersion\":\"v1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("order-clue-narrow-001"))
                .andExpect(jsonPath("$.fixtureVersion").value("t048b-order-clue-narrow-001-v1"));

        // Three delivered orders, of which *exactly one* answers to the clue. "Exactly one" is the whole
        // case: with two matching orders it would be the ambiguity case again, and with one order in total
        // there would be nothing for a filter to do. The other two are not decoration -- they are what
        // makes a COMPLETED run count as evidence that filtering happened.
        assertEquals(3, count("""
                        SELECT COUNT(*) FROM commerce.orders
                         WHERE id IN ('order-101','order-201','order-202') AND status = 'DELIVERED'
                        """));
        assertEquals(1, count("""
                        SELECT COUNT(*) FROM commerce.order_items
                         WHERE order_id IN ('order-101','order-201','order-202') AND product_name LIKE '%耳机%'
                        """));
        // Signed inside the window *relative to the reset* -- a literal timestamp is what rots, and every
        // one of the three has to be inside it, or "the filter chose" could be explained by eligibility.
        assertEquals(3, count("""
                        SELECT COUNT(*) FROM commerce.shipments
                         WHERE order_id IN ('order-101','order-201','order-202')
                           AND signed_at > now() - interval '7 days'
                        """));
        // Exactly one active rule may cover them. Two matching ruleCodes is a CONFLICTING_RULES refusal by
        // design, and that is what turned T042's second real run into a failure of the *fixture*: one
        // decoy would then be refusable for a reason that has nothing to do with the clue.
        assertEquals(1, count("""
                        SELECT COUNT(*) FROM commerce.after_sales_rules
                         WHERE active = TRUE AND required_order_status = 'DELIVERED'
                           AND (product_category IS NULL OR product_category = 'APPAREL')
                        """));
    }

    private void performReset(String token) throws Exception {
        mockMvc.perform(post("/internal/eval/fixtures/refund-logistics-001/reset")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"datasetVersion\":\"v1\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("refund-logistics-001"))
                .andExpect(jsonPath("$.datasetVersion").value("v1"))
                .andExpect(jsonPath("$.fixtureVersion").value("t014-refund-logistics-001-v1"))
                .andExpect(jsonPath("$.resetAt").exists());
    }

    private void seedAuthenticatedUser() {
        jdbcTemplate.update("""
                INSERT INTO commerce.users (id, username, role, status)
                VALUES ('customer-001', 'customer-001', 'CUSTOMER', 'ACTIVE')
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    role = EXCLUDED.role,
                    status = 'ACTIVE'
                """);
    }

    private int count(String sql) {
        Integer value = jdbcTemplate.queryForObject(sql, Integer.class);
        assertNotNull(value);
        return value;
    }
}
