package com.seventeen17.commerceagent.audit;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** 写入审计日志所需的结构化事实；不接受 raw token 或 hidden chain-of-thought。 */
public record AuditEvent(
        AuditActorType actorType,
        String actorId,
        String action,
        String resourceType,
        String resourceId,
        UUID runId,
        String result,
        Map<String, Object> metadata) {

    public AuditEvent {
        Objects.requireNonNull(actorType, "actorType must not be null");
        actorId = requireText(actorId, "actorId", 128);
        action = requireText(action, "action", 100);
        resourceType = requireText(resourceType, "resourceType", 100);
        resourceId = requireText(resourceId, "resourceId", 128);
        result = requireText(result, "result", 32);
        metadata = metadata == null ? Map.of() : Map.copyOf(new LinkedHashMap<>(metadata));
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(field + " exceeds max length " + maxLength);
        }
        return value;
    }
}
