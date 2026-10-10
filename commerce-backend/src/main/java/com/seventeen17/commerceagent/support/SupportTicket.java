package com.seventeen17.commerceagent.support;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Objects;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

/**
 * Durable handoff for after-sales work automation cannot safely complete.
 *
 * <p>This entity stores reviewable facts, not reasoning: one machine-readable reason code and one
 * bounded structured evidence summary. It contains no hidden chain-of-thought, raw prompt, token,
 * credential, or arbitrary endpoint.
 *
 * <p>Authorization deliberately does not live here. T060 must derive {@code userId} from the
 * authenticated principal and, when {@code orderId} is present, prove ownership before calling the
 * factory. {@code runId} is cross-service provenance only and never grants access.
 */
@Entity
@Table(name = "support_tickets")
public class SupportTicket {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    @Column(name = "user_id", length = 64, nullable = false, updatable = false)
    private String userId;

    @Column(name = "order_id", length = 64, updatable = false)
    private String orderId;

    @Column(name = "category", length = 64, nullable = false, updatable = false)
    private String category;

    @Column(name = "reason_code", length = 100, nullable = false, updatable = false)
    private String reasonCode;

    @Column(name = "evidence_summary", length = 2000, nullable = false, updatable = false)
    private String evidenceSummary;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 32, nullable = false)
    private SupportTicketStatus status;

    @Column(name = "run_id", length = 64, nullable = false, updatable = false)
    private String runId;

    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    @Generated(event = EventType.INSERT)
    @Column(name = "updated_at", nullable = false, insertable = false)
    private Instant updatedAt;

    protected SupportTicket() {}

    /**
     * Build a newly escalated ticket. New rows are always OPEN; callers cannot forge lifecycle
     * state during creation.
     */
    public static SupportTicket open(
            String id,
            String userId,
            String orderId,
            String category,
            String reasonCode,
            String evidenceSummary,
            String runId) {
        SupportTicket ticket = new SupportTicket();
        ticket.id = requireText(id, "id");
        ticket.userId = requireText(userId, "userId");
        ticket.orderId = blankToNull(orderId);
        ticket.category = requireText(category, "category");
        ticket.reasonCode = requireText(reasonCode, "reasonCode");
        ticket.evidenceSummary = requireText(evidenceSummary, "evidenceSummary");
        ticket.runId = requireText(runId, "runId");
        ticket.status = SupportTicketStatus.OPEN;
        return ticket;
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    public String getId() {
        return id;
    }

    public String getUserId() {
        return userId;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCategory() {
        return category;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public String getEvidenceSummary() {
        return evidenceSummary;
    }

    public SupportTicketStatus getStatus() {
        return status;
    }

    public String getRunId() {
        return runId;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
