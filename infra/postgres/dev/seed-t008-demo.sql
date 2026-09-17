\set ON_ERROR_STOP on

-- CommerceAgent T008 synthetic demo data
--
-- Purpose:
--   Give the local Adminer/PostgreSQL instance a medium-size, coherent dataset
--   so the T008 schema, foreign keys, indexes and Agent trace relationships are
--   easy to inspect before the real T014 fixture loader exists.
--
-- Important:
--   * Local development only; this is NOT a Flyway migration and is NOT T014.
--   * All business identifiers are prefixed with demo- so they are obvious.
--   * The script is idempotent: running it again will not duplicate demo rows.
--   * It intentionally seeds both commerce.* and agent.*; run it as postgres
--     only as a local setup action, never as an application runtime identity.
--
-- Approximate demo size after one run:
--   users 10 / orders 18 / order_items 33 / shipments 11 /
--   logistics_events 44 / after_sales_rules 7 / audit_logs 17 /
--   agent_runs 8 / tool_executions 23

BEGIN;

-- -----------------------------------------------------------------------------
-- Curated users
-- -----------------------------------------------------------------------------
INSERT INTO commerce.users (id, username, role, status, created_at)
VALUES
    ('demo-customer-001', 'demo.alice', 'CUSTOMER', 'ACTIVE', '2026-09-01 09:00:00+08'),
    ('demo-customer-002', 'demo.bob', 'CUSTOMER', 'ACTIVE', '2026-09-02 10:00:00+08'),
    ('demo-approver-001', 'demo.approver', 'APPROVER', 'ACTIVE', '2026-09-01 09:30:00+08'),
    ('demo-support-001', 'demo.support', 'SUPPORT', 'ACTIVE', '2026-09-01 09:45:00+08')
ON CONFLICT (id) DO NOTHING;

-- Extra customers make ownership/order relationships visible in Adminer.
INSERT INTO commerce.users (id, username, role, status, created_at)
SELECT
    'demo-customer-' || lpad(i::text, 3, '0'),
    'demo.customer' || lpad(i::text, 3, '0'),
    'CUSTOMER',
    CASE WHEN i = 8 THEN 'DISABLED' ELSE 'ACTIVE' END,
    '2026-09-03 09:00:00+08'::timestamptz + make_interval(days => i - 3)
FROM generate_series(3, 8) AS g(i)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Three curated orders for important future scenarios.
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

-- Fifteen generated orders cover every allowed order status three times.
INSERT INTO commerce.orders (
    id, user_id, status, total_amount, currency, created_at,
    shipped_at, delivered_at, after_sales_status, version
)
SELECT
    'demo-order-' || lpad(i::text, 3, '0'),
    'demo-customer-' || lpad((((i - 1) % 8) + 1)::text, 3, '0'),
    CASE i % 5
        WHEN 1 THEN 'PAID'
        WHEN 2 THEN 'SHIPPED'
        WHEN 3 THEN 'DELIVERED'
        WHEN 4 THEN 'CANCELLED'
        ELSE 'CLOSED'
    END,
    (70 + 20 * i)::numeric(19, 2),
    'CNY',
    '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i),
    CASE
        WHEN i % 5 IN (2, 3, 0)
            THEN '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i + 1)
        ELSE NULL
    END,
    CASE
        WHEN i % 5 IN (3, 0)
            THEN '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i + 3)
        ELSE NULL
    END,
    NULL,
    0
FROM generate_series(1, 15) AS g(i)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Curated order items
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

-- Every generated order gets two items. Their extended prices sum to order total:
-- item A = 40 + 10*i; item B = (15 + 5*i) * 2; total = 70 + 20*i.
INSERT INTO commerce.order_items (
    id, order_id, product_id, product_name, product_category, unit_price, quantity
)
SELECT
    'demo-item-' || lpad(i::text, 3, '0') || '-1',
    'demo-order-' || lpad(i::text, 3, '0'),
    'demo-product-' || lpad(i::text, 3, '0') || '-a',
    'Demo Product ' || lpad(i::text, 3, '0') || 'A',
    CASE i % 4
        WHEN 1 THEN 'electronics'
        WHEN 2 THEN 'accessories'
        WHEN 3 THEN 'home'
        ELSE 'apparel'
    END,
    (40 + 10 * i)::numeric(19, 2),
    1
FROM generate_series(1, 15) AS g(i)
ON CONFLICT (id) DO NOTHING;

INSERT INTO commerce.order_items (
    id, order_id, product_id, product_name, product_category, unit_price, quantity
)
SELECT
    'demo-item-' || lpad(i::text, 3, '0') || '-2',
    'demo-order-' || lpad(i::text, 3, '0'),
    'demo-product-' || lpad(i::text, 3, '0') || '-b',
    'Demo Product ' || lpad(i::text, 3, '0') || 'B',
    CASE i % 4
        WHEN 1 THEN 'accessories'
        WHEN 2 THEN 'home'
        WHEN 3 THEN 'apparel'
        ELSE 'electronics'
    END,
    (15 + 5 * i)::numeric(19, 2),
    2
FROM generate_series(1, 15) AS g(i)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Curated shipments
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

-- Generated SHIPPED / DELIVERED / CLOSED orders get one shipment each (9 rows).
INSERT INTO commerce.shipments (
    id, order_id, carrier, tracking_number, status,
    last_event_at, signed_at, version
)
SELECT
    'demo-shipment-' || lpad(i::text, 3, '0'),
    'demo-order-' || lpad(i::text, 3, '0'),
    CASE i % 3 WHEN 1 THEN 'SF' WHEN 2 THEN 'JD' ELSE 'YTO' END,
    'DEMO-GEN-' || lpad(i::text, 4, '0'),
    CASE WHEN i % 5 = 2 THEN 'IN_TRANSIT' ELSE 'DELIVERED' END,
    CASE
        WHEN i % 5 = 2
            THEN '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i + 2)
        ELSE '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i + 3)
    END,
    CASE
        WHEN i % 5 IN (3, 0)
            THEN '2026-08-20 10:00:00+08'::timestamptz + make_interval(days => i + 3)
        ELSE NULL
    END,
    0
FROM generate_series(1, 15) AS g(i)
WHERE i % 5 IN (2, 3, 0)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Curated logistics events. The stalled order intentionally stops at Sep 12.
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

-- Three baseline events for every generated shipment.
INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT
    'demo-shipment-' || lpad(i::text, 3, '0'),
    e.event_type,
    e.description,
    '2026-08-20 10:00:00+08'::timestamptz
        + make_interval(days => i + e.day_offset, hours => e.hour_offset)
FROM generate_series(1, 15) AS g(i)
CROSS JOIN (VALUES
    ('PICKED_UP', 'Package picked up by carrier', 1, 1),
    ('DEPARTED_HUB', 'Departed origin sorting hub', 1, 8),
    ('ARRIVED_HUB', 'Arrived destination sorting hub', 2, 0)
) AS e(event_type, description, day_offset, hour_offset)
WHERE i % 5 IN (2, 3, 0)
  AND NOT EXISTS (
      SELECT 1
      FROM commerce.logistics_events le
      WHERE le.shipment_id = 'demo-shipment-' || lpad(i::text, 3, '0')
        AND le.event_type = e.event_type
        AND le.occurred_at = '2026-08-20 10:00:00+08'::timestamptz
            + make_interval(days => i + e.day_offset, hours => e.hour_offset)
  );

-- Delivered/closed shipments get the final two events.
INSERT INTO commerce.logistics_events (shipment_id, event_type, description, occurred_at)
SELECT
    'demo-shipment-' || lpad(i::text, 3, '0'),
    e.event_type,
    e.description,
    '2026-08-20 10:00:00+08'::timestamptz
        + make_interval(days => i + e.day_offset, hours => e.hour_offset)
FROM generate_series(1, 15) AS g(i)
CROSS JOIN (VALUES
    ('OUT_FOR_DELIVERY', 'Courier is delivering the package', 2, 6),
    ('DELIVERED', 'Package signed by recipient', 3, 0)
) AS e(event_type, description, day_offset, hour_offset)
WHERE i % 5 IN (3, 0)
  AND NOT EXISTS (
      SELECT 1
      FROM commerce.logistics_events le
      WHERE le.shipment_id = 'demo-shipment-' || lpad(i::text, 3, '0')
        AND le.event_type = e.event_type
        AND le.occurred_at = '2026-08-20 10:00:00+08'::timestamptz
            + make_interval(days => i + e.day_offset, hours => e.hour_offset)
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
    ),
    (
        'DEMO_ACCESSORY_14D_RETURN', 1, 'accessories', 'DELIVERED',
        NULL, 14, 300.00, 250.00, 'RETURN_REFUND', TRUE,
        '2026-01-01 00:00:00+08', NULL
    ),
    (
        'DEMO_HOME_30D_RETURN', 1, 'home', 'DELIVERED',
        NULL, 30, 800.00, 600.00, 'RETURN', TRUE,
        '2026-01-01 00:00:00+08', NULL
    ),
    (
        'DEMO_CLOSED_ORDER_DENY', 1, NULL, 'CLOSED',
        NULL, NULL, 0.00, 0.00, 'DENY', TRUE,
        '2026-01-01 00:00:00+08', NULL
    ),
    (
        'DEMO_APPAREL_REVIEW', 1, 'apparel', NULL,
        NULL, 14, 1000.00, 500.00, 'MANUAL_REVIEW', TRUE,
        '2026-01-01 00:00:00+08', NULL
    )
ON CONFLICT (rule_code, version) DO NOTHING;

-- -----------------------------------------------------------------------------
-- One curated Agent run + two tool executions.
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

-- Seven additional runs deliberately cover different Agent terminal/wait states.
INSERT INTO agent.agent_runs (
    run_id, user_id, status, intent, resolved_order_id, current_node,
    next_action, step_count, retry_count, state_json, final_action,
    error_code, model_name, model_temperature, prompt_version,
    input_tokens, output_tokens, started_at, completed_at
)
SELECT
    ('20000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid,
    'demo-customer-' || lpad(i::text, 3, '0'),
    CASE i
        WHEN 1 THEN 'COMPLETED'
        WHEN 2 THEN 'WAITING_USER'
        WHEN 3 THEN 'WAITING_APPROVAL'
        WHEN 4 THEN 'ESCALATED'
        WHEN 5 THEN 'SAFE_STOP'
        WHEN 6 THEN 'FAILED'
        ELSE 'RUNNING'
    END,
    CASE i % 3
        WHEN 1 THEN 'REFUND_REQUEST'
        WHEN 2 THEN 'RETURN_REQUEST'
        ELSE 'CHECK_LOGISTICS'
    END,
    'demo-order-' || lpad(i::text, 3, '0'),
    CASE i
        WHEN 2 THEN 'await_clarification'
        WHEN 3 THEN 'await_approval'
        WHEN 5 THEN 'safe_stop'
        ELSE 'route_next_action'
    END,
    CASE i
        WHEN 2 THEN 'ASK_USER'
        WHEN 3 THEN 'WAIT_APPROVAL'
        WHEN 7 THEN 'GET_ORDER'
        ELSE NULL
    END,
    i + 2,
    CASE WHEN i IN (5, 6) THEN 1 ELSE 0 END,
    jsonb_build_object('demo', true, 'scenario', i, 'source', 'seed-t008-demo.sql'),
    CASE
        WHEN i = 1 THEN 'EXPLAIN_RESULT'
        WHEN i = 4 THEN 'CREATE_SUPPORT_TICKET_LATER'
        WHEN i = 5 THEN 'SAFE_STOP'
        ELSE NULL
    END,
    CASE WHEN i = 6 THEN 'DEMO_DEPENDENCY_FAILURE' ELSE NULL END,
    'demo-model',
    0.000,
    'demo-v1',
    100 + i * 17,
    40 + i * 9,
    '2026-09-17 20:10:00+08'::timestamptz + make_interval(minutes => i * 5),
    CASE
        WHEN i IN (1, 4, 5, 6)
            THEN '2026-09-17 20:10:00+08'::timestamptz + make_interval(minutes => i * 5, secs => 3)
        ELSE NULL
    END
FROM generate_series(1, 7) AS g(i)
ON CONFLICT (run_id) DO NOTHING;

-- Three tool executions per generated run make the run->tool 1:N relation visible.
INSERT INTO agent.tool_executions (
    run_id, step_index, tool_name, risk_level, input_summary,
    output_summary, status, error_code, retryable, latency_ms,
    trace_id, created_at
)
SELECT
    ('20000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid,
    s.step_index,
    s.tool_name,
    s.risk_level,
    jsonb_build_object('demo', true, 'order_id', 'demo-order-' || lpad(i::text, 3, '0')),
    jsonb_build_object('demo', true, 'step', s.step_index, 'scenario', i),
    CASE WHEN i = 6 AND s.step_index = 3 THEN 'ERROR' ELSE 'SUCCESS' END,
    CASE WHEN i = 6 AND s.step_index = 3 THEN 'DEMO_TIMEOUT' ELSE NULL END,
    i = 6 AND s.step_index = 3,
    30 + i * 7 + s.step_index * 5,
    'demo-trace-' || lpad(i::text, 3, '0'),
    '2026-09-17 20:10:00+08'::timestamptz
        + make_interval(minutes => i * 5, secs => s.step_index)
FROM generate_series(1, 7) AS g(i)
CROSS JOIN (VALUES
    (1, 'get_order', 'LOW'),
    (2, 'get_logistics', 'LOW'),
    (3, 'decide_next_evidence', 'MEDIUM')
) AS s(step_index, tool_name, risk_level)
ON CONFLICT (run_id, step_index) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Audit entries
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

-- One audit event per generated order (15 rows).
INSERT INTO commerce.audit_logs (
    actor_type, actor_id, action, resource_type, resource_id,
    run_id, result, metadata_json, created_at
)
SELECT
    CASE WHEN i % 3 = 0 THEN 'SYSTEM' ELSE 'AGENT' END,
    CASE WHEN i % 3 = 0 THEN 'demo-system' ELSE 'demo-agent' END,
    CASE i % 4
        WHEN 1 THEN 'ORDER_LOOKUP'
        WHEN 2 THEN 'LOGISTICS_LOOKUP'
        WHEN 3 THEN 'ELIGIBILITY_PREVIEW'
        ELSE 'ROUTE_PREVIEW'
    END,
    'ORDER',
    'demo-order-' || lpad(i::text, 3, '0'),
    CASE
        WHEN i <= 7
            THEN ('20000000-0000-4000-8000-' || lpad(i::text, 12, '0'))::uuid
        ELSE NULL
    END,
    CASE WHEN i = 12 THEN 'DENIED' ELSE 'SUCCESS' END,
    jsonb_build_object('demo', true, 'scenario_index', i),
    '2026-09-17 21:00:00+08'::timestamptz + make_interval(minutes => i)
FROM generate_series(1, 15) AS g(i)
WHERE NOT EXISTS (
    SELECT 1
    FROM commerce.audit_logs al
    WHERE al.resource_type = 'ORDER'
      AND al.resource_id = 'demo-order-' || lpad(i::text, 3, '0')
      AND al.metadata_json ->> 'scenario_index' = i::text
);

COMMIT;

SELECT 'T008_DEMO_SEED_OK' AS result;

-- Quick counts for Adminer/psql verification.
WITH demo_counts AS (
    SELECT 'commerce.users' AS table_name, COUNT(*)::bigint AS row_count
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
    FROM agent.tool_executions
    WHERE trace_id LIKE 'demo-trace-%'
)
SELECT table_name, row_count
FROM demo_counts
UNION ALL
SELECT 'TOTAL_DEMO_ROWS', SUM(row_count)
FROM demo_counts
ORDER BY table_name;
