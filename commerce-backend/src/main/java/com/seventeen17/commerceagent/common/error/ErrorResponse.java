package com.seventeen17.commerceagent.common.error;

import java.util.Map;

public record ErrorResponse(
        ErrorCode errorCode, String message, boolean retryable, String traceId, Map<String, Object> details) {

    public ErrorResponse {
        details = details == null ? Map.of() : Map.copyOf(details);
    }
}
