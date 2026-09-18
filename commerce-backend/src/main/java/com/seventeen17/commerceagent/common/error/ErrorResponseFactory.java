package com.seventeen17.commerceagent.common.error;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ErrorResponseFactory {

    public ErrorResponse create(HttpServletRequest request, ErrorCode errorCode) {
        return create(request, errorCode, errorCode.defaultMessage(), Map.of());
    }

    public ErrorResponse create(
            HttpServletRequest request, ErrorCode errorCode, String message, Map<String, Object> details) {
        return new ErrorResponse(
                errorCode,
                message,
                errorCode.retryable(),
                TraceIdFilter.currentOrCreate(request),
                details);
    }
}
