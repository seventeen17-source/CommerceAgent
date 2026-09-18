package com.seventeen17.commerceagent.common.error;

public enum ErrorCode {
    AUTH_REQUIRED(401, false, "Authentication is required"),
    ACCESS_DENIED(403, false, "Access is denied"),
    ORDER_NOT_FOUND(404, false, "Order was not found"),
    ORDER_FORBIDDEN(403, false, "Order is not accessible to the authenticated user"),
    AMBIGUOUS_ORDER(409, false, "Multiple orders match the request"),
    INVALID_ORDER_STATE(409, false, "Order state does not allow the requested action"),
    LOGISTICS_UNAVAILABLE(503, true, "Logistics information is temporarily unavailable"),
    POLICY_NOT_FOUND(404, false, "Applicable policy evidence was not found"),
    POLICY_VERSION_CONFLICT(409, false, "Applicable policy version cannot be determined"),
    ELIGIBILITY_DENIED(422, false, "After-sales eligibility was denied"),
    MANUAL_REVIEW_REQUIRED(422, false, "Manual review is required"),
    APPROVAL_REQUIRED(422, false, "Approval is required"),
    APPROVAL_DENIED(409, false, "Approval was denied"),
    APPROVAL_EXPIRED(409, false, "Approval has expired"),
    INVALID_PARAMETER(400, false, "Request parameter validation failed"),
    AMOUNT_EXCEEDS_ALLOWED(422, false, "Requested amount exceeds the allowed amount"),
    IDEMPOTENCY_CONFLICT(409, false, "Idempotency key conflicts with an existing request"),
    DUPLICATE_AFTER_SALES(409, false, "A conflicting after-sales request already exists"),
    WRITE_TIMEOUT_UNKNOWN(504, false, "Write result is unknown after timeout"),
    DEPENDENCY_TIMEOUT(504, true, "A dependency timed out"),
    DEPENDENCY_UNAVAILABLE(503, true, "A required dependency is unavailable"),
    TOOL_NOT_ALLOWED(403, false, "The requested tool is not allowed"),
    MAX_STEPS_EXCEEDED(422, false, "Agent step budget was exceeded"),
    REPEATED_NO_PROGRESS(422, false, "Agent made no progress after repeated attempts"),
    POST_WRITE_VERIFICATION_FAILED(502, false, "Post-write state could not be verified"),
    PROMPT_INJECTION_BLOCKED(403, false, "Protected instructions or permissions cannot be overridden"),
    INTERNAL_ERROR(500, false, "Internal server error");

    private final int httpStatus;
    private final boolean retryable;
    private final String defaultMessage;

    ErrorCode(int httpStatus, boolean retryable, String defaultMessage) {
        this.httpStatus = httpStatus;
        this.retryable = retryable;
        this.defaultMessage = defaultMessage;
    }

    public int httpStatus() {
        return httpStatus;
    }

    public boolean retryable() {
        return retryable;
    }

    public String defaultMessage() {
        return defaultMessage;
    }
}
