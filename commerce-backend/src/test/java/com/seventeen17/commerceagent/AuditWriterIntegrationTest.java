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

/** T013：验证结构化审计持久化、敏感数据护栏和两类事务边界。 */
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
        long id = auditWriter.writeBusinessEvent(new AuditEvent(
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
        assertThrows(IllegalArgumentException.class, () -> auditWriter.writeSecurityEvent(rawToken));

        AuditEvent jwtValue = eventWithMetadata(Map.of(
                "safeKey", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjdXN0b21lci0wMDEifQ.abcdefghijklmnopqrstuvwxyz123456"));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.writeSecurityEvent(jwtValue));

        AuditEvent embeddedJwt = eventWithMetadata(
                Map.of(
                        "note",
                        "auth used eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjdXN0b21lci0wMDEifQ.abcdefghijklmnopqrstuvwxyz123456 to call"));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.writeSecurityEvent(embeddedJwt));

        AuditEvent embeddedBearer = eventWithMetadata(Map.of("note", "request used Bearer secret-token before denial"));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.writeSecurityEvent(embeddedBearer));

        AuditEvent hiddenReasoning =
                eventWithMetadata(Map.of("nested", Map.of("chainOfThought", List.of("private reasoning"))));
        assertThrows(IllegalArgumentException.class, () -> auditWriter.writeSecurityEvent(hiddenReasoning));
    }

    @Test
    void rejectsRawCredentialsInTopLevelAuditFields() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new AuditEvent(
                        AuditActorType.USER,
                        "customer Bearer short-secret",
                        "SECURITY_DECISION",
                        "ORDER",
                        "order-t013",
                        null,
                        "DENIED",
                        Map.of()));

        assertThrows(
                IllegalArgumentException.class,
                () -> new AuditEvent(
                        AuditActorType.USER,
                        "customer-t013",
                        "SECURITY_DECISION",
                        "ORDER",
                        "prefix eyJhbGciOiJIUzI1NiJ9.abcdefghijk.lmnopqrstuv suffix",
                        null,
                        "DENIED",
                        Map.of()));
    }

    @Test
    void metadataIsSnapshottedBeforePersistence() {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("traceId", "trace-original");
        AuditEvent event = eventWithMetadata(metadata);
        metadata.put("traceId", "trace-mutated-after-event-created");

        long id = auditWriter.writeSecurityEvent(event);

        AuditLog saved = repository.findById(id).orElseThrow();
        assertEquals("trace-original", saved.getMetadataJson().get("traceId"));
    }

    @Test
    void businessAuditJoinsOuterTransactionAndRollsBackWithIt() {
        String resourceId = "order-t013-business-rollback";
        TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);

        transactionTemplate.executeWithoutResult(status -> {
            auditWriter.writeBusinessEvent(new AuditEvent(
                    AuditActorType.SYSTEM,
                    "commerce-backend",
                    "REFUND_REQUEST_CREATE",
                    "ORDER",
                    resourceId,
                    null,
                    "SUCCESS",
                    Map.of("traceId", "trace-business-rollback")));
            status.setRollbackOnly();
        });

        assertFalse(
                repository.findByActionAndResourceIdOrderByCreatedAtAsc("REFUND_REQUEST_CREATE", resourceId).stream()
                        .findAny()
                        .isPresent());
    }

    @Test
    void securityAuditSurvivesOuterTransactionRollback() {
        String resourceId = "order-t013-security-denied";
        TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);

        transactionTemplate.executeWithoutResult(status -> {
            auditWriter.writeSecurityEvent(new AuditEvent(
                    AuditActorType.SYSTEM,
                    "commerce-backend",
                    "ORDER_ACCESS_DENIED",
                    "ORDER",
                    resourceId,
                    null,
                    "DENIED",
                    Map.of("traceId", "trace-security-denied")));
            status.setRollbackOnly();
        });

        assertEquals(
                1,
                repository
                        .findByActionAndResourceIdOrderByCreatedAtAsc("ORDER_ACCESS_DENIED", resourceId)
                        .size());
    }

    @Test
    void allowsStructuredReasonCodesWithoutHiddenReasoning() {
        long id = auditWriter.writeSecurityEvent(eventWithMetadata(
                Map.of("reasonCodes", List.of("LOGISTICS_STALLED", "WITHIN_AMOUNT_LIMIT"), "eligible", true)));

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
