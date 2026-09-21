package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * T017 的 schema 前提：**并发 resume 的仲裁能力必须由数据库提供**，而不是靠应用层"记得检查"。
 *
 * <p>这是 T009 {@code OrderConcurrencyGuaranteesTest} 的同类测试，针对 Agent run：
 *
 * <ul>
 *   <li>{@code version} 列是 compare-and-set 的暗号。没有它，{@code SELECT ... FOR UPDATE} 只能把两个
 *       resume 请求**串行化**，第二个请求醒来后仍然会按自己读到的旧快照继续推进 —— 阻塞不等于检测到过期。
 *   <li>{@code chk_agent_runs_terminal_has_completion} 把"终态"与"有完成时间"绑在一起。retention 依赖
 *       "终态且已完成"来决定能否回收，如果 COMPLETED 却 {@code completed_at IS NULL}，retention 就无法
 *       一致地判断。
 *   <li>{@code agent.agent_checkpoints} 的 {@code UNIQUE (run_id, version)} 与 {@code ON DELETE CASCADE}
 *       是 checkpoint 历史的两条硬保证。
 * </ul>
 *
 * <p>刻意不标注 {@code @Transactional}：每条语句都必须自己提交，否则 SQL 错误只会让事务进入 aborted
 * 状态，而测试仍然会"通过"到一个误导性的结论。这里用 {@link Transactional} 的 {@code NOT_SUPPORTED}
 * 模式显式声明这一意图。
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class AgentRunCheckpointSchemaTests {

    /**
     * V001 的必要列：NOT NULL 且无默认值，插入测试行时必须显式给出。
     *
     * <p>这两个时间戳都取 **数据库时钟**，而不是 {@code java.time.Instant.now()}。原因是一次真实踩坑：
     * 第一次写成 JDBC 传 {@code completed_at}、{@code started_at} 用数据库默认值，结果
     * {@code chk_agent_runs_completion_time}（{@code completed_at >= started_at}）直接拒绝 ——
     * 数据库容器的时区与 JVM 时区不同，两个时钟相差 8 小时。**跨时钟比较时间戳本身就是不可靠的**，
     * 所以这里让两者出自同一个时钟。
     */
    private static final String INSERT_RUN = """
            INSERT INTO agent.agent_runs (
                run_id, user_id, status, model_name, prompt_version, started_at, completed_at
            )
            VALUES (
                ?, ?, ?, 'gpt-4o-mini', 't017-v1', CURRENT_TIMESTAMP,
                CASE WHEN ? THEN CURRENT_TIMESTAMP + INTERVAL '1 second' ELSE NULL END
            )
            """;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void newRunStartsWithVersionOneAndNoCompactionMark() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "RUNNING");

        assertEquals(1, versionOf(runId), "version 必须从 1 开始，避免让读方特判'尚无版本'");
        assertNull(compactedAtOf(runId), "新 run 的 checkpoint_compacted_at 必须为 NULL");
    }

    @Test
    void versionCannotBeZeroOrNegative() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "RUNNING");

        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbcTemplate.update("UPDATE agent.agent_runs SET version = 0 WHERE run_id = ?", runId),
                "version 是 CAS 暗号，0 或负数必须被数据库拒绝");

        assertEquals("23514", sqlStateOf(exception), "必须是 PostgreSQL check_violation");
    }

    @Test
    void terminalStatusRequiresCompletionTime() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "RUNNING");

        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbcTemplate.update("UPDATE agent.agent_runs SET status = 'COMPLETED' WHERE run_id = ?", runId),
                "COMPLETED 但 completed_at IS NULL 是一种 retention 无法处理的矛盾状态");

        assertEquals("23514", sqlStateOf(exception), "必须是 PostgreSQL check_violation");
    }

    @Test
    void waitingStatusCannotClaimACompletionTime() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "WAITING_APPROVAL");

        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbcTemplate.update(
                        "UPDATE agent.agent_runs SET completed_at = CURRENT_TIMESTAMP WHERE run_id = ?", runId),
                "等待中的 run 已经'完成'意味着它可以被 retention 回收 —— 那会删掉一个还需要 resume 的 checkpoint");

        assertEquals("23514", sqlStateOf(exception), "必须是 PostgreSQL check_violation");
    }

    @Test
    void aCheckpointVersionCannotBeWrittenTwice() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "WAITING_APPROVAL");
        insertCheckpoint(runId, 1, "WAITING_APPROVAL");

        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> insertCheckpoint(runId, 1, "WAITING_APPROVAL"),
                "同一 (run_id, version) 的第二条 checkpoint 必须被拒绝：否则'那次 resume 到底写了什么'没有唯一答案");

        assertEquals("23505", sqlStateOf(exception), "必须是 PostgreSQL unique_violation");
    }

    @Test
    void checkpointRequiresAnExistingRun() {
        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> insertCheckpoint(UUID.randomUUID(), 1, "RUNNING"),
                "checkpoint 不能悬空指向不存在的 run");

        assertEquals("23503", sqlStateOf(exception), "必须是 PostgreSQL foreign_key_violation");
    }

    @Test
    void deletingARunRemovesItsCheckpoints() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "FAILED", true);
        insertCheckpoint(runId, 1, "RUNNING");
        insertCheckpoint(runId, 2, "FAILED");

        jdbcTemplate.update("DELETE FROM agent.agent_runs WHERE run_id = ?", runId);

        assertEquals(0, countCheckpoints(runId), "删除 run 必须级联删除 checkpoint，不留孤儿行");
    }

    @Test
    void retentionMarkerCanBeSetWithoutTouchingStatus() {
        UUID runId = UUID.randomUUID();
        insertRun(runId, "COMPLETED", true);
        insertCheckpoint(runId, 1, "COMPLETED");

        int updated = jdbcTemplate.update(
                "UPDATE agent.agent_runs SET state_json = '{}'::jsonb, checkpoint_compacted_at = CURRENT_TIMESTAMP"
                        + " WHERE run_id = ?",
                runId);

        assertEquals(1, updated);
        assertNotNull(compactedAtOf(runId), "回收后必须留下'已回收'的证据，否则无法区分'没有状态'和'状态被删了'");
        assertEquals(
                "COMPLETED",
                jdbcTemplate.queryForObject(
                        "SELECT status FROM agent.agent_runs WHERE run_id = ?", String.class, runId));
    }

    @Test
    void retentionScanIndexExistsForStatusAndStartTime() {
        Boolean indexExists = jdbcTemplate.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'agent'"
                        + " AND indexname = 'idx_agent_runs_status_started')",
                Boolean.class);

        assertTrue(Boolean.TRUE.equals(indexExists), "retention 按 status + started_at 扫描，需要复合索引");
    }

    private void insertRun(UUID runId, String status) {
        insertRun(runId, status, false);
    }

    /**
     * 终态与 completed_at 必须一起给：V002 的 {@code chk_agent_runs_terminal_has_completion} 不允许
     * "COMPLETED 但没有完成时间"，所以不能先插 RUNNING 再 UPDATE —— 那正是这条约束要禁止的中间状态。
     */
    private void insertRun(UUID runId, String status, boolean completed) {
        jdbcTemplate.update(INSERT_RUN, runId, "t017-user", status, completed);
    }

    private void insertCheckpoint(UUID runId, int version, String status) {
        jdbcTemplate.update(
                "INSERT INTO agent.agent_checkpoints (run_id, version, status, state_json)"
                        + " VALUES (?, ?, ?, '{}'::jsonb)",
                runId,
                version,
                status);
    }

    private int versionOf(UUID runId) {
        Integer version = jdbcTemplate.queryForObject(
                "SELECT version FROM agent.agent_runs WHERE run_id = ?", Integer.class, runId);
        assertNotNull(version);
        return version;
    }

    private Object compactedAtOf(UUID runId) {
        return jdbcTemplate.queryForObject(
                "SELECT checkpoint_compacted_at FROM agent.agent_runs WHERE run_id = ?", Object.class, runId);
    }

    private int countCheckpoints(UUID runId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM agent.agent_checkpoints WHERE run_id = ?", Integer.class, runId);
        assertNotNull(count);
        return count;
    }

    private static String sqlStateOf(DataIntegrityViolationException exception) {
        Throwable current = exception;
        while (current != null) {
            if (current instanceof java.sql.SQLException sqlException) {
                return sqlException.getSQLState();
            }
            current = current.getCause();
        }
        throw new AssertionError("异常链中没有 SQLException", exception);
    }
}
