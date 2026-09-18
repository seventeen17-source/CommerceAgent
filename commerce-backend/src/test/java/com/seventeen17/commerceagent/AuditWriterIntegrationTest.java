package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditLog;
import com.seventeen17.commerceagent.audit.AuditLogRepository;
import com.seventeen17.commerceagent.audit.AuditWriter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** T013：验证结构化审计持久化、敏感数据护栏和业务事务回滚语义。 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class AuditWriterIntegrationTest {

    @Autowired
    private AuditWriter auditWriter;

    @Autowired
    private AuditLogRepository repository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void writesStructuredAuditEvent() {
        UUID runId = UUID.randomUUID();
        long id = auditWriter.write(new AuditEvent(
                AuditActorType.USER,
                "customer-t013",
                "REFUND_REQUEST_CREATE",
                "ORDER",
                "order-t013",
                runId,
                "SUCCESS",
                Map.of("traceId", "trace-t013", "reasonCode", "LOGISTICS_STALLED")));

        AuditLog saved = repository.findById(id).orElseThrow();
        assertEquals(AuditActorType.USER, saved.getActorType());
        assertEquals("customer-t013", saved.getActorId());
        assertEquals("REFUND_REQUEST_CREATE", saved.getAction());
        assertEquals("ORDER", saved.getResourceType());
        assertEquals("order-t013", saved.getResourceId());
        assertEquals(runId, saved.getRunId());
        assertEquals("SUCCESS", saved.getResult());
        assertEquals("trace-t013", saved.getMetadataJson().get("traceId"));
        assertEquals("LOGISTICS_STALLED", saved.getMetadataJson().get("reasonCode"));
        assertNotNull(saved.getCreatedAt());
    }

    @Test
    void rejectsRawCredentialsAndHiddenReasoningRecursively() {
        AuditEvent rawToken = eventWithMetadata(Map.of("authorization", "Bearer secret-token"));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.write(rawToken));

        AuditEvent jwtValue = eventWithMetadata(Map.of(
                "safeKey",
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjdXN0b21lci0wMDEifQ.abcdefghijklmnopqrstuvwxyz123456"));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.write(jwtValue));

        AuditEvent hiddenReasoning = eventWithMetadata(
                Map.of("nested", Map.of("chainOfThought", List.of("private reasoning"))));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.write(hiddenReasoning));
    }

    @Test
    void metadataIsSnapshottedBeforePersistence() {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("traceId", "trace-original");
        AuditEvent event = eventWithMetadata(metadata);
        metadata.put("traceId", "trace-mutated-after-event-created");

        long id = auditWriter.write(event);

        AuditLog saved = repository.findById(id).orElseThrow();
        assertEquals("trace-original", saved.getMetadataJson().get("traceId"));
    }

    @Test
    void auditJoinsBusinessTransactionAndRollsBackWithIt() {
        String resourceId = "order-t013-rollback";
        TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);

        transactionTemplate.executeWithoutResult(status -> {
            auditWriter.write(new AuditEvent(
                    AuditActorType.SYSTEM,
                    "commerce-backend",
                    "REFUND_REQUEST_CREATE",
                    "ORDER",
                    resourceId,
                    null,
                    "SUCCESS",
                    Map.of("traceId", "trace-rollback")));
            status.setRollbackOnly();
        });

        assertFalse(repository
                .findByActionAndResourceIdOrderByCreatedAtAsc("REFUND_REQUEST_CREATE", resourceId)
                .stream()
                .findAny()
                .isPresent());
    }

    @Test
    void allowsStructuredReasonCodesWithoutHiddenReasoning() {
        long id = auditWriter.write(eventWithMetadata(Map.of(
                "reasonCodes", List.of("LOGISTICS_STALLED", "WITHIN_AMOUNT_LIMIT"),
                "eligible", true)));

        AuditLog saved = repository.findById(id).orElseThrow();
        assertTrue(saved.getMetadataJson().containsKey("reasonCodes"));
    }

    private static AuditEvent eventWithMetadata(Map<String, Object> metadata) {
        return new AuditEvent(
                AuditActorType.SYSTEM,
                "commerce-backend",
                "SECURITY_DECISION",
                "ORDER",
                "order-t013-metadata",
                null,
                "DENIED",
                metadata);
    }
}
