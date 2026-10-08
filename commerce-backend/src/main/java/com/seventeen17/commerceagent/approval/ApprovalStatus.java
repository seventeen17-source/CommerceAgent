package com.seventeen17.commerceagent.approval;

/**
 * Authoritative lifecycle of one human approval request.
 *
 * <p>Only {@link #PENDING} may transition. The other three values are terminal facts: once a human
 * (or the expiry rule) has decided the request, later callers may not rewrite that history.
 */
public enum ApprovalStatus {
    PENDING,
    APPROVED,
    DENIED,
    EXPIRED
}
