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

        jdbcTemplate.update("UPDATE commerce.orders SET status = 'CANCELLED' WHERE id = 'order-001'");
        performReset(token);

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
