\set ON_ERROR_STOP on

-- CommerceAgent T008 synthetic demo data
--
-- Purpose:
--   Give the local Adminer/PostgreSQL instance a small, coherent dataset so the
--   T008 schema and relationships are easy to inspect before the real T014
--   fixture loader exists.
--
-- Important:
--   * Local development only; this is NOT a Flyway migration and is NOT T014.
--   * All business identifiers are prefixed with demo- so they are obvious.
--   * The script is idempotent: running it again will not duplicate demo rows.
--   * It intentionally seeds both commerce.* and agent.*; run it as postgres
--     only as a local setup action, never as an application runtime identity.

BEGIN;

-- -----------------------------------------------------------------------------
-- Users
-- -----------------------------------------------------------------------------
INSERT INTO commerce.users (id, username, role, status, created_at)
VALUES
    ('demo-customer-001', 'demo.alice', 'CUSTOMER', 'ACTIVE', '2026-09-01 09:00:00+08'),
    ('demo-customer-002', 'demo.bob', 'CUSTOMER', 'ACTIVE', '2026-09-02 10:00:00+08'),
    ('demo-approver-001', 'demo.approver', 'APPROVER', 'ACTIVE', '2026-09-01 09:30:00+08'),
    ('demo-support-001', 'demo.support', 'SUPPORT', 'ACTIVE', '2026-09-01 09:45:00+08')
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Orders: deliberately cover different states for later Agent routing demos.
-- -----------------------------------------------------------------------------
INSERT INTO commerce.orders (
    id, user_id, status, total_amount, currency, created_at,
    shipped_at, delivered_at, after_sales_status, version
)
VALUES
    (
        'demo-order-stalled-001', 'demo-customer-001', 'SHIPPED', 299.00, 'CNY',
        '2026-09-10 10:00:00+08', '2026-09-11 09:00:00+08', NULL, NULL, 0
    ),
    (
        'demo-order-delivered-001', 'demo-customer-001', 'DELIVERED', 89.90, 'CNY',
        '2026-09-08 11:00:00+08', '2026-09-09 08:30:00+08', '2026-09-12 14:20:00+08', NULL, 0
    ),
    (
        'demo-order-highvalue-001', 'demo-customer-002', 'PAID', 1299.00, 'CNY',
        '2026-09-16 19:30:00+08', NULL, NULL, NULL, 0
    )
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Order items
-- -----------------------------------------------------------------------------
INSERT INTO commerce.order_items (
    id, order_id, product_id, product_name, product_category, unit_price, quantity
)
VALUES
    (
        'demo-item-stalled-001', 'demo-order-stalled-001', 'demo-product-headset-001',
        'Wireless Headset', 'electronics', 299.00, 1
    ),
    (
        'demo-item-delivered-001', 'demo-order-delivered-001', 'demo-product-cable-001',
        'USB-C Cable', 'accessories', 44.95, 2
    ),
    (
        'demo-item-highvalue-001', 'demo-order-highvalue-001', 'demo-product-tablet-001',
        'Android Tablet', 'electronics', 1299.00, 1
    )
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Shipments
-- -----------------------------------------------------------------------------
INSERT INTO commerce.shipments (
    id, order_id, carrier, tracking_number, status,
    last_event_at, signed_at, version
)
VALUES
    (
        'demo-shipment-stalled-001', 'demo-order-stalled-001', 'SF', 'DEMO-SF-0001',
        'IN_TRANSIT', '2026-09-12 08:15:00+08', NULL, 0
    ),
    (
        'demo-shipment-delivered-001', 'demo-order-delivered-001', 'JD', 'DEMO-JD-0001',
        'DELIVERED', '2026-09-12 14:20:00+08', '2026-09-12 14:20:00+08', 0
    )
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Logistics events. The stalled order intentionally has no event after Sep 12.
-- -----------------------------------------------------------------------------
INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT 'demo-shipment-stalled-001', 'PICKED_UP', 'Package picked up by carrier', '2026-09-11 09:20:00+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.logistics_events
    WHERE shipment_id = 'demo-shipment-stalled-001'
      AND event_type = 'PICKED_UP'
      AND occurred_at = '2026-09-11 09:20:00+08'
);

INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT 'demo-shipment-stalled-001', 'ARRIVED_HUB', 'Arrived at regional sorting hub', '2026-09-12 08:15:00+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.logistics_events
    WHERE shipment_id = 'demo-shipment-stalled-001'
      AND event_type = 'ARRIVED_HUB'
      AND occurred_at = '2026-09-12 08:15:00+08'
);

INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT 'demo-shipment-delivered-001', 'PICKED_UP', 'Package picked up by carrier', '2026-09-09 09:00:00+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.logistics_events
    WHERE shipment_id = 'demo-shipment-delivered-001'
      AND event_type = 'PICKED_UP'
      AND occurred_at = '2026-09-09 09:00:00+08'
);

INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT 'demo-shipment-delivered-001', 'OUT_FOR_DELIVERY', 'Courier is delivering the package', '2026-09-12 09:10:00+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.logistics_events
    WHERE shipment_id = 'demo-shipment-delivered-001'
      AND event_type = 'OUT_FOR_DELIVERY'
      AND occurred_at = '2026-09-12 09:10:00+08'
);

INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT 'demo-shipment-delivered-001', 'DELIVERED', 'Package signed by recipient', '2026-09-12 14:20:00+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.logistics_events
    WHERE shipment_id = 'demo-shipment-delivered-001'
      AND event_type = 'DELIVERED'
      AND occurred_at = '2026-09-12 14:20:00+08'
);

-- -----------------------------------------------------------------------------
-- Deterministic after-sales rules
-- -----------------------------------------------------------------------------
INSERT INTO commerce.after_sales_rules (
    rule_code, version, product_category, required_order_status,
    logistics_stalled_hours, return_window_days, max_refund_amount,
    approval_threshold, allowed_action, active, effective_from, effective_to
)
VALUES
    (
        'DEMO_STALLED_72H_REFUND', 1, NULL, 'SHIPPED',
        72, NULL, 500.00, 300.00, 'REFUND_ONLY', TRUE,
        '2026-01-01 00:00:00+08', NULL
    ),
    (
        'DEMO_DELIVERED_7D_RETURN', 1, NULL, 'DELIVERED',
        NULL, 7, 500.00, 300.00, 'RETURN_REFUND', TRUE,
        '2026-01-01 00:00:00+08', NULL
    ),
    (
        'DEMO_HIGH_VALUE_MANUAL', 1, 'electronics', NULL,
        NULL, NULL, 2000.00, 1000.00, 'MANUAL_REVIEW', TRUE,
        '2026-01-01 00:00:00+08', NULL
    )
ON CONFLICT (rule_code, version) DO NOTHING;

-- -----------------------------------------------------------------------------
-- One synthetic Agent run + two tool executions, only to make agent.* visible.
-- No real model/tool execution has happened yet.
-- -----------------------------------------------------------------------------
INSERT INTO agent.agent_runs (
    run_id, user_id, status, intent, resolved_order_id, current_node,
    next_action, step_count, retry_count, state_json, final_action,
    error_code, model_name, model_temperature, prompt_version,
    input_tokens, output_tokens, started_at, completed_at
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'demo-customer-001',
    'COMPLETED',
    'CHECK_LOGISTICS',
    'demo-order-stalled-001',
    'verify_evidence',
    NULL,
    2,
    0,
    '{"demo": true, "note": "synthetic T008 visualization only"}'::jsonb,
    'EXPLAIN_STALLED_LOGISTICS',
    NULL,
    'demo-model',
    0.000,
    'demo-v1',
    120,
    56,
    '2026-09-17 20:00:00+08',
    '2026-09-17 20:00:02+08'
)
ON CONFLICT (run_id) DO NOTHING;

INSERT INTO agent.tool_executions (
    run_id, step_index, tool_name, risk_level, input_summary,
    output_summary, status, error_code, retryable, latency_ms,
    trace_id, created_at
)
VALUES
    (
        '11111111-1111-4111-8111-111111111111', 1, 'get_order', 'LOW',
        '{"order_id": "demo-order-stalled-001"}'::jsonb,
        '{"status": "SHIPPED", "total_amount": 299.00}'::jsonb,
        'SUCCESS', NULL, FALSE, 42, 'demo-trace-001', '2026-09-17 20:00:01+08'
    ),
    (
        '11111111-1111-4111-8111-111111111111', 2, 'get_logistics', 'LOW',
        '{"order_id": "demo-order-stalled-001"}'::jsonb,
        '{"shipment_status": "IN_TRANSIT", "last_event_at": "2026-09-12T08:15:00+08:00"}'::jsonb,
        'SUCCESS', NULL, FALSE, 51, 'demo-trace-001', '2026-09-17 20:00:02+08'
    )
ON CONFLICT (run_id, step_index) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Audit entries corresponding to the synthetic visualization flow.
-- -----------------------------------------------------------------------------
INSERT INTO commerce.audit_logs (
    actor_type, actor_id, action, resource_type, resource_id,
    run_id, result, metadata_json, created_at
)
SELECT
    'SYSTEM', 'demo-seed', 'DEMO_DATA_SEEDED', 'DATABASE', 'commerceagent',
    NULL, 'SUCCESS', '{"demo": true, "task": "T008"}'::jsonb,
    '2026-09-17 19:59:59+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.audit_logs
    WHERE actor_type = 'SYSTEM'
      AND actor_id = 'demo-seed'
      AND action = 'DEMO_DATA_SEEDED'
      AND resource_id = 'commerceagent'
);

INSERT INTO commerce.audit_logs (
    actor_type, actor_id, action, resource_type, resource_id,
    run_id, result, metadata_json, created_at
)
SELECT
    'AGENT', 'demo-agent', 'READ_LOGISTICS', 'ORDER', 'demo-order-stalled-001',
    '11111111-1111-4111-8111-111111111111', 'SUCCESS',
    '{"demo": true, "latest_event": "ARRIVED_HUB"}'::jsonb,
    '2026-09-17 20:00:02+08'
WHERE NOT EXISTS (
    SELECT 1 FROM commerce.audit_logs
    WHERE run_id = '11111111-1111-4111-8111-111111111111'
      AND action = 'READ_LOGISTICS'
      AND resource_id = 'demo-order-stalled-001'
);

COMMIT;

SELECT 'T008_DEMO_SEED_OK' AS result;

-- Quick counts for Adminer/psql verification.
SELECT 'commerce.users' AS table_name, COUNT(*) AS row_count
FROM commerce.users WHERE id LIKE 'demo-%'
UNION ALL
SELECT 'commerce.orders', COUNT(*) FROM commerce.orders WHERE id LIKE 'demo-%'
UNION ALL
SELECT 'commerce.order_items', COUNT(*) FROM commerce.order_items WHERE id LIKE 'demo-%'
UNION ALL
SELECT 'commerce.shipments', COUNT(*) FROM commerce.shipments WHERE id LIKE 'demo-%'
UNION ALL
SELECT 'commerce.logistics_events', COUNT(*)
FROM commerce.logistics_events WHERE shipment_id LIKE 'demo-%'
UNION ALL
SELECT 'commerce.after_sales_rules', COUNT(*)
FROM commerce.after_sales_rules WHERE rule_code LIKE 'DEMO_%'
UNION ALL
SELECT 'commerce.audit_logs', COUNT(*)
FROM commerce.audit_logs WHERE actor_id LIKE 'demo-%'
UNION ALL
SELECT 'agent.agent_runs', COUNT(*)
FROM agent.agent_runs WHERE user_id LIKE 'demo-%'
UNION ALL
SELECT 'agent.tool_executions', COUNT(*)
FROM agent.tool_executions WHERE run_id = '11111111-1111-4111-8111-111111111111';
