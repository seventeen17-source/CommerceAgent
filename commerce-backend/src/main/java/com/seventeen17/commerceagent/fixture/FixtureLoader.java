package com.seventeen17.commerceagent.fixture;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile({"dev", "test", "eval"})
public class FixtureLoader {

    private static final Logger log = LoggerFactory.getLogger(FixtureLoader.class);
    private static final String RESET_LOCK_NAME = "commerceagent-eval-fixture-reset";
    private static final Instant FIXTURE_CREATED_AT = Instant.parse("2026-09-01T00:00:00Z");
    private static final Instant ORDER_SHIPPED_AT = Instant.parse("2026-09-10T08:00:00Z");
    private static final Instant LAST_LOGISTICS_EVENT_AT = Instant.parse("2026-09-12T08:00:00Z");

    /**
     * The literal signing time the older fixtures use.
     *
     * <p>Named rather than inlined because it is the *reason* T042's case cannot reuse them: paired with
     * a 7-day window it stopped being "inside the window" on 2026-09-19, so a case built on it would be
     * graded against {@code RETURN_WINDOW_EXPIRED} -- a fixture that rots looks exactly like a product
     * regression.
     */
    private static final Instant LEGACY_DELIVERED_AT = Instant.parse("2026-09-12T10:00:00Z");

    /** T042: the eval case whose world must stay inside the return window whenever it is reset. */
    static final String RETURN_DELIVERED_CASE = "return-delivered-001";

    private static final String RETURN_DELIVERED_ORDER_ID = "order-003";
    private static final String RETURN_DELIVERED_SHIPMENT_ID = "shipment-003";
    private static final String RETURN_DELIVERED_RULE_CODE = "RETURN_DELIVERED_WINDOW";
    private static final int RETURN_WINDOW_DAYS = 7;
    private static final Duration SIGNED_AGO = Duration.ofDays(3);

    /** T048: the ambiguity case -- two writable-looking orders that the same product clue describes. */
    static final String AMBIGUOUS_ORDER_CASE = "order-ambiguous-001";

    private static final String AMBIGUOUS_ORDER_FIRST_ID = "order-101";
    private static final String AMBIGUOUS_ORDER_SECOND_ID = "order-102";

    private final JdbcTemplate jdbcTemplate;
    private final FixtureCaseRegistry registry;
    private final Clock clock;

    @Autowired
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
                "SELECT pg_try_advisory_xact_lock(CAST(hashtext(?) AS BIGINT))", Boolean.class, RESET_LOCK_NAME);
        if (!Boolean.TRUE.equals(acquired)) {
            throw new BusinessException(ErrorCode.EVAL_RESET_CONFLICT);
        }

        try {
            clearFixtureState();
            seedBaseUsers();
            // T042: the two cases need *different* worlds, and the difference is not cosmetic. Seeding
            // both leaves customer-001 holding a shipped order and a delivered one, so the resolver has
            // two candidates for one request and asks instead of guessing -- correct US3 behaviour, wrong
            // case: the first real run of this case ended WAITING_USER with no write at all. The return
            // case therefore seeds only its own world.
            if (RETURN_DELIVERED_CASE.equals(fixtureCase.caseId())) {
                seedDeliveredReturnCase();
            } else if (AMBIGUOUS_ORDER_CASE.equals(fixtureCase.caseId())) {
                seedAmbiguousOrderCase();
            } else {
                seedRefundLogisticsCase();
            }
            return new FixtureResetResponse(
                    fixtureCase.caseId(), fixtureCase.datasetVersion(), fixtureCase.fixtureVersion(), clock.instant());
        } catch (BusinessException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            log.error(
                    "Eval fixture reset failed caseId={} datasetVersion={}",
                    caseId,
                    fixtureCase.datasetVersion(),
                    exception);
            throw new BusinessException(ErrorCode.EVAL_RESET_FAILED, "Eval fixture reset failed", exception);
        }
    }

    @Transactional
    public void seedDevelopmentFixtures() {
        // pg_advisory_xact_lock returns `void`, not boolean -- unlike pg_try_advisory_xact_lock in
        // reset(). Mapping a void result to Boolean makes the driver read an empty string and throw
        // "cannot cast to boolean", so the blocking form is read as Object and its value ignored:
        // the lock is held for the rest of this transaction either way.
        jdbcTemplate.queryForObject(
                "SELECT pg_advisory_xact_lock(CAST(hashtext(?) AS BIGINT))", Object.class, RESET_LOCK_NAME);
        seedBaseUsers();
        seedRefundLogisticsCase();
    }

    private void clearFixtureState() {
        jdbcTemplate.update("DELETE FROM commerce.audit_logs");
        // T021/T026：refund_requests 对 orders 有外键，因此必须在下游对象之后再删 orders，否则 fixture reset 会以
        // FK 违约失败。Eval reset 的语义是"业务状态回到基线"，退款这类写入结果必须一起清掉，否则"重置后重跑同一个
        // 用例"会因为上一轮的退款行而得到不同结论。
        jdbcTemplate.update(
                "DELETE FROM commerce.refund_requests WHERE order_id IN ('order-001', 'order-002', 'order-003', 'order-101', 'order-102')");
        // T038：退货行与退款行同类 —— 都是"运行产生的写入结果"，不是用例的起点。同样必须在删 orders 之前
        // 处理掉（同样的外键），否则"重置后重跑同一个用例"会带着上一轮的退货行，结论不可比。
        jdbcTemplate.update(
                "DELETE FROM commerce.return_requests WHERE order_id IN ('order-001', 'order-002', 'order-003', 'order-101', 'order-102')");
        jdbcTemplate.update(
                "DELETE FROM commerce.logistics_events WHERE shipment_id IN ('shipment-001', 'shipment-002', 'shipment-003', 'shipment-101', 'shipment-102')");
        jdbcTemplate.update(
                "DELETE FROM commerce.shipments WHERE order_id IN ('order-001', 'order-002', 'order-003', 'order-101', 'order-102')");
        jdbcTemplate.update(
                "DELETE FROM commerce.order_items WHERE order_id IN ('order-001', 'order-002', 'order-003', 'order-101', 'order-102')");
        jdbcTemplate.update(
                "DELETE FROM commerce.orders WHERE id IN ('order-001', 'order-002', 'order-003', 'order-101', 'order-102')");
        // The eval world must not inherit policy rows it did not choose. Deleting only the two rule codes
        // this loader creates left the demo seed's rules in place, and a delivered order then matched both
        // a demo return rule and this case's rule: two distinct ruleCodes matching one order is a
        // CONFLICTING_RULES refusal by design, so the case graded a *correct* refusal as a failure. Found by
        // running it -- status COMPLETED, zero return rows, zero Tool calls.
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules");
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id IN ('customer-001', 'customer-002', 'approver-001')");
    }

    private void seedBaseUsers() {
        upsertUser("customer-001", "customer-001", "CUSTOMER");
        upsertUser("customer-002", "customer-002", "CUSTOMER");
        upsertUser("approver-001", "approver-001", "APPROVER");
    }

    private void upsertUser(String id, String username, String role) {
        jdbcTemplate.update("""
                INSERT INTO commerce.users (id, username, role, status, created_at)
                VALUES (?, ?, ?, 'ACTIVE', ?)
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    role = EXCLUDED.role,
                    status = EXCLUDED.status
                """, id, username, role, Timestamp.from(FIXTURE_CREATED_AT));
    }

    /**
     * T042: the world US2's eval case needs -- delivered, and *inside* the return window.
     *
     * <p>The signing timestamp is derived from the injected {@link Clock}, not written as a literal.
     * That is the whole point: the window is relative by nature ("within N days of signing"), so a
     * fixture that pins an absolute timestamp is only accidentally inside it, and stops being so once
     * the calendar moves. Deriving it means the case asks the same question in 2026 and in 2036.
     */
    private void seedDeliveredReturnCase() {
        Instant signedAt = clock.instant().minus(SIGNED_AGO);
        upsertOrder(RETURN_DELIVERED_ORDER_ID, "customer-001", "DELIVERED", "120.00", signedAt);
        upsertOrderItem("item-003", RETURN_DELIVERED_ORDER_ID, "product-003", "Linen Shirt", "APPAREL", "120.00");
        upsertShipmentSignedAt(
                RETURN_DELIVERED_SHIPMENT_ID,
                RETURN_DELIVERED_ORDER_ID,
                "SYNTHETIC",
                "TRACK-003",
                "DELIVERED",
                signedAt);
        ensureLogisticsEvent(RETURN_DELIVERED_SHIPMENT_ID, "DELIVERED", "Synthetic signed delivery event", signedAt);
        upsertReturnRule();
    }

    /**
     * T048: two orders that one product clue describes -- both of them writable-looking.
     *
     * <p>The point of the fixture is that *not writing* has to be a decision rather than an accident:
     * both orders are delivered, inside the return window, and covered by a rule that grants
     * {@code RETURN_REFUND}. A run that guessed would therefore leave a real return row behind, which is
     * exactly what the eval case asserts must not exist.
     */
    private void seedAmbiguousOrderCase() {
        Instant signedAt = clock.instant().minus(SIGNED_AGO);
        seedAmbiguousOrder(AMBIGUOUS_ORDER_FIRST_ID, "item-101", "product-101", "无线蓝牙耳机 Pro", "shipment-101", signedAt);
        seedAmbiguousOrder(
                AMBIGUOUS_ORDER_SECOND_ID, "item-102", "product-102", "有线耳机 Basic", "shipment-102", signedAt);
        upsertReturnRule();
    }

    private void seedAmbiguousOrder(
            String orderId, String itemId, String productId, String productName, String shipmentId, Instant signedAt) {
        upsertOrder(orderId, "customer-001", "DELIVERED", "199.00", signedAt);
        upsertOrderItem(itemId, orderId, productId, productName, "APPAREL", "199.00");
        upsertShipmentSignedAt(shipmentId, orderId, "SYNTHETIC", "TRACK-" + orderId, "DELIVERED", signedAt);
        ensureLogisticsEvent(shipmentId, "DELIVERED", "Synthetic signed delivery event", signedAt);
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
        upsertOrder(id, userId, status, totalAmount, LEGACY_DELIVERED_AT);
    }

    private void upsertOrder(String id, String userId, String status, String totalAmount, Instant deliveredAt) {
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
                "DELIVERED".equals(status) ? Timestamp.from(deliveredAt) : null);
    }

    private void upsertOrderItem(
            String id, String orderId, String productId, String productName, String productCategory, String unitPrice) {
        jdbcTemplate.update("""
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
                """, id, orderId, productId, productName, productCategory, unitPrice);
    }

    private void upsertShipment(String id, String orderId, String carrier, String trackingNumber, String status) {
        upsertShipmentSignedAt(id, orderId, carrier, trackingNumber, status, LEGACY_DELIVERED_AT);
    }

    /**
     * The signing time is a parameter (T042) so a case can say "signed three days ago" instead of
     * inheriting whatever the calendar has done to a literal.
     */
    private void upsertShipmentSignedAt(
            String id, String orderId, String carrier, String trackingNumber, String status, Instant deliveredAt) {
        Instant eventTime = "DELIVERED".equals(status) ? deliveredAt : LAST_LOGISTICS_EVENT_AT;
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

    /*
     * Check-then-insert is safe only because every fixture mutation path acquires RESET_LOCK_NAME
     * for the surrounding database transaction. Do not reuse this method outside that boundary.
     */
    private void ensureLogisticsEvent(String shipmentId, String eventType, String description, Instant occurredAt) {
        Integer count =
                jdbcTemplate.queryForObject("""
                SELECT COUNT(*)
                FROM commerce.logistics_events
                WHERE shipment_id = ? AND event_type = ? AND occurred_at = ?
                """, Integer.class, shipmentId, eventType, Timestamp.from(occurredAt));
        if (count != null && count == 0) {
            jdbcTemplate.update("""
                    INSERT INTO commerce.logistics_events
                        (shipment_id, event_type, description, occurred_at)
                    VALUES (?, ?, ?, ?)
                    """, shipmentId, eventType, description, Timestamp.from(occurredAt));
        }
    }

    private void upsertAfterSalesRule() {
        jdbcTemplate.update("""
                INSERT INTO commerce.after_sales_rules
                    (rule_code, version, product_category, required_order_status,
                     logistics_stalled_hours, return_window_days, max_refund_amount,
                     approval_threshold, allowed_action, active, effective_from, effective_to)
                VALUES
                    ('LOGISTICS_STALLED_REFUND', 1, 'ELECTRONICS', 'SHIPPED',
                     48, 7, 500.00, 300.00, 'REFUND_ONLY', TRUE, ?, NULL)
                ON CONFLICT (rule_code, version) DO UPDATE
                SET active = TRUE
                """, Timestamp.from(FIXTURE_CREATED_AT));
    }

    /**
     * The rule T042's case runs against: a delivered order may be *returned* inside a window.
     *
     * <p>{@code logistics_stalled_hours} is NULL on purpose. A return rule that declared a stall
     * threshold would make a signed shipment trip the stall branch's conflict check
     * ({@code LOGISTICS_CONFLICTS_WITH_ORDER}) and send every legitimate return to manual review --
     * the trap T039 recorded and pinned with a test of its own.
     */
    private void upsertReturnRule() {
        jdbcTemplate.update("""
                INSERT INTO commerce.after_sales_rules
                    (rule_code, version, product_category, required_order_status,
                     logistics_stalled_hours, return_window_days, max_refund_amount,
                     approval_threshold, allowed_action, active, effective_from, effective_to)
                VALUES (?, 1, 'APPAREL', 'DELIVERED', NULL, ?, 500.00, 1000.00, 'RETURN_REFUND', TRUE, ?, NULL)
                ON CONFLICT (rule_code, version) DO UPDATE
                SET active = TRUE, return_window_days = EXCLUDED.return_window_days
                """, RETURN_DELIVERED_RULE_CODE, RETURN_WINDOW_DAYS, Timestamp.from(FIXTURE_CREATED_AT));
    }
}
