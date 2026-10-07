package com.seventeen17.commerceagent.audit;

/** 与 commerce.audit_logs.actor_type CHECK 约束一致。 */
public enum AuditActorType {
    USER,
    AGENT,
    APPROVER,
    SYSTEM
}
