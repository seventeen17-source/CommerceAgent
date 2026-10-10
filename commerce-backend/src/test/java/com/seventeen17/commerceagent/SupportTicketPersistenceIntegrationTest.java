package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.support.SupportTicket;
import com.seventeen17.commerceagent.support.SupportTicketRepository;
import com.seventeen17.commerceagent.support.SupportTicketStatus;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class SupportTicketPersistenceIntegrationTest {

    private static final String USER_ID = "t059-customer";
    private static final String OTHER_USER_ID = "t059-other";
    private static final String ORDER_ID = "t059-order";

    @Autowired
    private SupportTicketRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void newTicketIsOpenAndPersistsStructuredEscalationFacts() {
        seedUser(USER_ID);
        seedOrder(ORDER_ID, USER_ID);

        SupportTicket ticket = repository.saveAndFlush(SupportTicket.open(
                UUID.randomUUID().toString(),
                USER_ID,
                ORDER_ID,
                "AFTER_SALES_ESCALATION",
                "MANUAL_REVIEW_REQUIRED",
                "LOGISTICS status=IN_TRANSIT; stalledHours=unknown",
                "59595959-1111-4222-8333-444444444444"));

        assertEquals(SupportTicketStatus.OPEN, ticket.getStatus());
        assertEquals(USER_ID, ticket.getUserId());
        assertEquals(ORDER_ID, ticket.getOrderId());
        assertEquals("MANUAL_REVIEW_REQUIRED", ticket.getReasonCode());
        assertEquals("LOGISTICS status=IN_TRANSIT; stalledHours=unknown", ticket.getEvidenceSummary());
        assertTrue(ticket.getCreatedAt() != null);
        assertTrue(ticket.getUpdatedAt() != null);
    }

    @Test
    void unresolvedOrderMayBeAbsentWithoutLosingOwnerOrRunProvenance() {
        seedUser(USER_ID);

        SupportTicket ticket = repository.saveAndFlush(SupportTicket.open(
                UUID.randomUUID().toString(),
                USER_ID,
                null,
                "DEPENDENCY_FAILURE",
                "ORDER_UNRESOLVED",
                "No authoritative order could be established",
                "59595959-2222-4333-8444-555555555555"));

        assertNull(ticket.getOrderId());
        assertEquals(USER_ID, ticket.getUserId());
        assertEquals("59595959-2222-4333-8444-555555555555", ticket.getRunId());
    }

    @Test
    void ownerScopedRepositoryCannotReadAnotherCustomersTicket() {
        seedUser(USER_ID);
        seedUser(OTHER_USER_ID);

        SupportTicket ticket = repository.saveAndFlush(SupportTicket.open(
                UUID.randomUUID().toString(),
                OTHER_USER_ID,
                null,
                "AFTER_SALES_ESCALATION",
                "MANUAL_REVIEW_REQUIRED",
                "Structured evidence",
                "59595959-3333-4444-8555-666666666666"));

        assertTrue(repository.findByIdAndUserId(ticket.getId(), USER_ID).isEmpty());
        assertTrue(repository.findByIdAndUserId(ticket.getId(), OTHER_USER_ID).isPresent());
    }

    @AfterEach
    void cleanT059Rows() {
        jdbcTemplate.update("DELETE FROM commerce.support_tickets WHERE user_id LIKE 't059-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id LIKE 't059-%'");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id LIKE 't059-%'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id LIKE 't059-%'");
    }

    private void seedUser(String userId) {
        jdbcTemplate.update("""
                INSERT INTO commerce.users (id, username, role, status, created_at)
                VALUES (?, ?, 'CUSTOMER', 'ACTIVE', CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING
                """, userId, userId);
    }

    private void seedOrder(String orderId, String userId) {
        jdbcTemplate.update("""
                INSERT INTO commerce.orders
                    (id, user_id, status, total_amount, currency, created_at, after_sales_status, version)
                VALUES (?, ?, 'SHIPPED', 199.00, 'USD', CURRENT_TIMESTAMP, NULL, 0)
                """, orderId, userId);
    }
}
