package com.seventeen17.commerceagent.fixture;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile({"dev", "test", "eval"})
public class FixtureLoader {

    private static final String RESET_LOCK_NAME = "commerceagent-eval-fixture-reset";
    private static final Instant FIXTURE_CREATED_AT = Instant.parse("2026-09-01T00:00:00Z");
    private static final Instant ORDER_SHIPPED_AT = Instant.parse("2026-09-10T08:00:00Z");
    private static final Instant LAST_LOGISTICS_EVENT_AT = Instant.parse("2026-09-12T08:00:00Z");

    private final JdbcTemplate jdbcTemplate;
    private final FixtureCaseRegistry registry;
    private final Clock clock;

    public FixtureLoader(JdbcTemplate jdbcTemplate, FixtureCaseRegistry registry) {
        this(jdbcTemplate, registry, Clock.systemUTC());
    }

    FixtureLoader(JdbcTemplate jdbcTemplate, FixtureCaseRegistry registry, Clock clock) {
        this.jdbcTemplate = jdbcTemplate;
        this.registry = registry;
        this.clock = clock;
    }

    @Transactional
    public FixtureResetResponse reset(String caseId, String datasetVersion) {
        FixtureCase fixtureCase = registry.find(caseId, datasetVersion)
                .orElseThrow(() -> new BusinessException(
                        ErrorCode.EVAL_CASE_NOT_FOUND, "Eval fixture case or dataset version was not found"));

        Boolean acquired = jdbcTemplate.queryForObject(
                "SELECT pg_try_advisory_xact_lock(CAST(hashtext(?) AS BIGINT))",
                Boolean.class,
                RESET_LOCK_NAME);
        if (!Boolean.TRUE.equals(acquired)) {
            throw new BusinessException(ErrorCode.EVAL_RESET_CONFLICT);
        }

        try {
            clearFixtureState();
            seedBaseUsers();
            seedRefundLogisticsCase();
            return new FixtureResetResponse(
                    fixtureCase.caseId(), fixtureCase.datasetVersion(), fixtureCase.fixtureVersion(), clock.instant());
        } catch (BusinessException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new BusinessException(ErrorCode.EVAL_RESET_FAILED, "Eval fixture reset failed");
        }
    }

    @Transactional
    public void seedDevelopmentFixtures() {
        seedBaseUsers();
        seedRefundLogisticsCase();
    }

    private void clearFixtureState() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs");
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id IN ('shipment-001', 'shipment-002')");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE order_id IN ('order-001', 'order-002')");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id IN ('order-001', 'order-002')");
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id IN ('order-001', 'order-002')");
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code = 'LOGISTICS_STALLED_REFUND'");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id IN ('customer-001', 'customer-002', 'approver-001')");
    }

    private void seedBaseUsers() {
        upsertUser("customer-001", "customer-001", "CUSTOMER");
        upsertUser("customer-002", "customer-002", "CUSTOMER");
        upsertUser("approver-001", "approver-001", "APPROVER");
    }

    private void upsertUser(String id, String username, String role) {
        jdbcTemplate.update(
                """
                INSERT INTO commerce.users (id, username, role, status, created_at)
                VALUES (?, ?, ?, 'ACTIVE', ?)
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    role = EXCLUDED.role,
                    status = EXCLUDED.status
                """,
                id,
                username,
                role,
                Timestamp.from(FIXTURE_CREATED_AT));
    }

    private void seedRefundLogisticsCase() {
        upsertOrder("order-001", "customer-001", "SHIPPED", "199.00");
        upsertOrder("order-002", "customer-002", "DELIVERED", "89.00");
        upsertOrderItem("item-001", "order-001", "product-001", "Wireless Headphones", "ELECTRONICS", "199.00");
        upsertOrderItem("item-002", "order-002", "product-002", "Travel Mug", "HOME", "89.00");
        upsertShipment("shipment-001", "order-001", "SYNTHETIC", "TRACK-001", "IN_TRANSIT");
        upsertShipment("shipment-002", "order-002", "SYNTHETIC", "TRACK-002", "DELIVERED");
        ensureLogisticsEvent(
                "shipment-001", "IN_TRANSIT", "Synthetic stalled logistics event", LAST_LOGISTICS_EVENT_AT);
        ensureLogisticsEvent(
                "shipment-002",
                "DELIVERED",
                "Synthetic delivered logistics event",
                Instant.parse("2026-09-12T10:00:00Z"));
        upsertAfterSalesRule();
    }

    private void upsertOrder(String id, String userId, String status, String totalAmount) {
        jdbcTemplate.update(
                """
                INSERT INTO commerce.orders
                    (id, user_id, status, total_amount, currency, created_at, shipped_at, delivered_at,
                     after_sales_status, version)
                VALUES (?, ?, ?, CAST(? AS NUMERIC), 'USD', ?, ?, ?, NULL, 0)
                ON CONFLICT (id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    status = EXCLUDED.status,
                    total_amount = EXCLUDED.total_amount,
                    shipped_at = EXCLUDED.shipped_at,
                    delivered_at = EXCLUDED.delivered_at,
                    after_sales_status = NULL,
                    version = 0
                """,
                id,
                userId,
                status,
                totalAmount,
                Timestamp.from(FIXTURE_CREATED_AT),
                Timestamp.from(ORDER_SHIPPED_AT),
                "DELIVERED".equals(status) ? Timestamp.from(Instant.parse("2026-09-12T10:00:00Z")) : null);
    }

    private void upsertOrderItem(
            String id,
            String orderId,
            String productId,
            String productName,
            String productCategory,
            String unitPrice) {
        jdbcTemplate.update(
                """
                INSERT INTO commerce.order_items
                    (id, order_id, product_id, product_name, product_category, unit_price, quantity)
                VALUES (?, ?, ?, ?, ?, CAST(? AS NUMERIC), 1)
                ON CONFLICT (id) DO UPDATE
                SET order_id = EXCLUDED.order_id,
                    product_id = EXCLUDED.product_id,
                    product_name = EXCLUDED.product_name,
                    product_category = EXCLUDED.product_category,
                    unit_price = EXCLUDED.unit_price,
                    quantity = EXCLUDED.quantity
                """,
                id,
                orderId,
                productId,
                productName,
                productCategory,
                unitPrice);
    }

    private void upsertShipment(String id, String orderId, String carrier, String trackingNumber, String status) {
        Instant eventTime =
                "DELIVERED".equals(status) ? Instant.parse("2026-09-12T10:00:00Z") : LAST_LOGISTICS_EVENT_AT;
        Instant signedAt = "DELIVERED".equals(status) ? eventTime : null;
        jdbcTemplate.update(
                """
                INSERT INTO commerce.shipments
                    (id, order_id, carrier, tracking_number, status, last_event_at, signed_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (id) DO UPDATE
                SET order_id = EXCLUDED.order_id,
                    carrier = EXCLUDED.carrier,
                    tracking_number = EXCLUDED.tracking_number,
                    status = EXCLUDED.status,
                    last_event_at = EXCLUDED.last_event_at,
                    signed_at = EXCLUDED.signed_at,
                    version = 0
                """,
                id,
                orderId,
                carrier,
                trackingNumber,
                status,
                Timestamp.from(eventTime),
                signedAt == null ? null : Timestamp.from(signedAt));
    }

    private void ensureLogisticsEvent(String shipmentId, String eventType, String description, Instant occurredAt) {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM commerce.logistics_events
                WHERE shipment_id = ? AND event_type = ? AND occurred_at = ?
                """,
                Integer.class,
                shipmentId,
                eventType,
                Timestamp.from(occurredAt));
        if (count != null && count == 0) {
            jdbcTemplate.update(
                    """
                    INSERT INTO commerce.logistics_events
                        (shipment_id, event_type, description, occurred_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    shipmentId,
                    eventType,
                    description,
                    Timestamp.from(occurredAt));
        }
    }

    private void upsertAfterSalesRule() {
        jdbcTemplate.update(
                """
                INSERT INTO commerce.after_sales_rules
                    (rule_code, version, product_category, required_order_status,
                     logistics_stalled_hours, return_window_days, max_refund_amount,
                     approval_threshold, allowed_action, active, effective_from, effective_to)
                VALUES
                    ('LOGISTICS_STALLED_REFUND', 1, 'ELECTRONICS', 'SHIPPED',
                     48, 7, 500.00, 300.00, 'REFUND_ONLY', TRUE, ?, NULL)
                ON CONFLICT (rule_code, version) DO UPDATE
                SET active = TRUE
                """,
                Timestamp.from(FIXTURE_CREATED_AT));
    }
}
