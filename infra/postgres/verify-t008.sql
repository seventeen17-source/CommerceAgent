\set ON_ERROR_STOP on

-- CommerceAgent T008 local acceptance checks.
-- Run as postgres against the local commerceagent database after Flyway migration.

DO $$
DECLARE
    missing_tables text[];
BEGIN
    SELECT array_agg(table_name)
    INTO missing_tables
    FROM (
        VALUES
            ('commerce.users'),
            ('commerce.orders'),
            ('commerce.order_items'),
            ('commerce.shipments'),
            ('commerce.logistics_events'),
            ('commerce.after_sales_rules'),
            ('commerce.audit_logs'),
            ('agent.agent_runs'),
            ('agent.tool_executions')
    ) AS expected(table_name)
    WHERE to_regclass(expected.table_name) IS NULL;

    IF missing_tables IS NOT NULL THEN
        RAISE EXCEPTION 'T008 missing tables: %', missing_tables;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM commerce.flyway_schema_history
        WHERE version = '001' AND success = true
    ) THEN
        RAISE EXCEPTION 'Flyway V001 is not recorded as successful';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'vector extension must remain disabled in T008';
    END IF;

    IF has_schema_privilege('agent_app', 'commerce', 'USAGE') THEN
        RAISE EXCEPTION 'agent_app unexpectedly has USAGE on commerce schema';
    END IF;

    IF has_table_privilege('agent_app', 'commerce.orders', 'SELECT') THEN
        RAISE EXCEPTION 'agent_app unexpectedly has SELECT on commerce.orders';
    END IF;

    IF NOT has_schema_privilege('agent_app', 'agent', 'USAGE') THEN
        RAISE EXCEPTION 'agent_app is missing USAGE on agent schema';
    END IF;

    IF NOT has_table_privilege('agent_app', 'agent.agent_runs', 'SELECT') THEN
        RAISE EXCEPTION 'agent_app is missing SELECT on agent.agent_runs';
    END IF;

    IF NOT has_table_privilege('commerce_app', 'commerce.orders', 'SELECT') THEN
        RAISE EXCEPTION 'commerce_app is missing SELECT on commerce.orders';
    END IF;
END
$$;

SELECT 'T008_ACCEPTANCE_OK' AS result;
