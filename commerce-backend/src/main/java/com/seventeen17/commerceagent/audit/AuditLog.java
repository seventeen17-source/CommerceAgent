package com.seventeen17.commerceagent.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.hibernate.annotations.Generated;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.generator.EventType;
import org.hibernate.type.SqlTypes;

/** commerce.audit_logs 的 append-only 持久化映射。 */
@Entity
@Table(name = "audit_logs")
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false, updatable = false)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "actor_type", length = 20, nullable = false, updatable = false)
    private AuditActorType actorType;

    @Column(name = "actor_id", length = 128, nullable = false, updatable = false)
    private String actorId;

    @Column(name = "action", length = 100, nullable = false, updatable = false)
    private String action;

    @Column(name = "resource_type", length = 100, nullable = false, updatable = false)
    private String resourceType;

    @Column(name = "resource_id", length = 128, nullable = false, updatable = false)
    private String resourceId;

    @Column(name = "run_id", updatable = false)
    private UUID runId;

    @Column(name = "result", length = 32, nullable = false, updatable = false)
    private String result;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "metadata_json", nullable = false, updatable = false, columnDefinition = "jsonb")
    private Map<String, Object> metadataJson = Map.of();

    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    protected AuditLog() {}

    static AuditLog from(AuditEvent event) {
        AuditLog log = new AuditLog();
        log.actorType = event.actorType();
        log.actorId = event.actorId();
        log.action = event.action();
        log.resourceType = event.resourceType();
        log.resourceId = event.resourceId();
        log.runId = event.runId();
        log.result = event.result();
        log.metadataJson = Map.copyOf(new LinkedHashMap<>(event.metadata()));
        return log;
    }

    public Long getId() {
        return id;
    }

    public AuditActorType getActorType() {
        return actorType;
    }

    public String getActorId() {
        return actorId;
    }

    public String getAction() {
        return action;
    }

    public String getResourceType() {
        return resourceType;
    }

    public String getResourceId() {
        return resourceId;
    }

    public UUID getRunId() {
        return runId;
    }

    public String getResult() {
        return result;
    }

    public Map<String, Object> getMetadataJson() {
        return Map.copyOf(metadataJson);
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
