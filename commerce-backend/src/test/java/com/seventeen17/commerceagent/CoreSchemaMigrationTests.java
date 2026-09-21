package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class CoreSchemaMigrationTests {

    private static final Set<String> EXPECTED_CORE_TABLES = Set.of(
            "commerce.users",
            "commerce.orders",
            "commerce.order_items",
            "commerce.shipments",
            "commerce.logistics_events",
            "commerce.after_sales_rules",
            "commerce.audit_logs",
            "agent.agent_runs",
            "agent.tool_executions",
            // T017: checkpoint history, written in the same transaction as the run row it describes.
            "agent.agent_checkpoints");

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void flywayCreatesAllT008CoreTables() {
        List<String> actualTables = jdbcTemplate.queryForList("""
                SELECT table_schema || '.' || table_name
                FROM information_schema.tables
                WHERE table_schema IN ('commerce', 'agent')
                  AND table_type = 'BASE TABLE'
                """, String.class);

        assertTrue(
                actualTables.containsAll(EXPECTED_CORE_TABLES),
                () -> "Missing T008 core tables. Expected=" + EXPECTED_CORE_TABLES + ", actual=" + actualTables);
    }

    @Test
    void flywayVersion001Succeeded() {
        Integer count = jdbcTemplate.queryForObject("""
                SELECT COUNT(*)
                FROM commerce.flyway_schema_history
                WHERE version = '001'
                  AND success = true
                """, Integer.class);

        assertEquals(1, count);
    }

    @Test
    void t008DoesNotEnableVectorExtension() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'", Integer.class);

        assertEquals(0, count);
    }
}
