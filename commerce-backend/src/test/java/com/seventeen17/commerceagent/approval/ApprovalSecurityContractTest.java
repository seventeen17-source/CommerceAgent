package com.seventeen17.commerceagent.approval;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class ApprovalSecurityContractTest {

    private static final Instant EXPIRES_AT = Instant.parse("2026-10-09T12:00:00Z");
    private static final Instant DECIDED_AT = Instant.parse("2026-10-08T12:00:00Z");
    private static final CommercePrincipal APPROVER =
            new CommercePrincipal("approver-001", UserRole.APPROVER);

    @Test
    void pendingCanBecomeApprovedAndRecordsWhoDecided() {
        ApprovalRequest request = refundApproval();

        request.approve(APPROVER, DECIDED_AT);

        assertEquals(ApprovalStatus.APPROVED, request.getStatus());
        assertEquals("approver-001", request.getDecidedBy());
        assertEquals(DECIDED_AT, request.getDecidedAt());
    }

    @Test
    void pendingCanBecomeDenied() {
        ApprovalRequest request = refundApproval();

        request.deny(APPROVER, DECIDED_AT);

        assertEquals(ApprovalStatus.DENIED, request.getStatus());
        assertEquals("approver-001", request.getDecidedBy());
        assertEquals(DECIDED_AT, request.getDecidedAt());
    }

    @Test
    void pendingCanBecomeExpiredWithoutPretendingAHumanDecidedIt() {
        ApprovalRequest request = refundApproval();

        request.expire(DECIDED_AT);

        assertEquals(ApprovalStatus.EXPIRED, request.getStatus());
        assertNull(request.getDecidedBy());
        assertEquals(DECIDED_AT, request.getDecidedAt());
    }

    @Test
    void everyTerminalDecisionIsIrreversibleAndKeepsTheOriginalDecisionMetadata() {
        ApprovalRequest approved = refundApproval();
        approved.approve(APPROVER, DECIDED_AT);

        Instant later = DECIDED_AT.plusSeconds(60);
        assertThrows(IllegalStateException.class, () -> approved.deny(APPROVER, later));
        assertThrows(IllegalStateException.class, () -> approved.expire(later));

        assertEquals(ApprovalStatus.APPROVED, approved.getStatus());
        assertEquals("approver-001", approved.getDecidedBy());
        assertEquals(DECIDED_AT, approved.getDecidedAt());

        ApprovalRequest denied = refundApproval();
        denied.deny(APPROVER, DECIDED_AT);
        assertThrows(IllegalStateException.class, () -> denied.approve(APPROVER, later));

        ApprovalRequest expired = refundApproval();
        expired.expire(DECIDED_AT);
        assertThrows(IllegalStateException.class, () -> expired.approve(APPROVER, later));
    }

    @Test
    void nonApproverCannotApproveOrDenyAndFailureDoesNotMutateTheRequest() {
        for (UserRole role : new UserRole[] {UserRole.CUSTOMER, UserRole.SUPPORT}) {
            ApprovalRequest request = refundApproval();
            CommercePrincipal principal = new CommercePrincipal("not-an-approver", role);

            BusinessException approveFailure =
                    assertThrows(BusinessException.class, () -> request.approve(principal, DECIDED_AT));
            assertEquals(ErrorCode.ACCESS_DENIED, approveFailure.getErrorCode());

            BusinessException denyFailure =
                    assertThrows(BusinessException.class, () -> request.deny(principal, DECIDED_AT));
            assertEquals(ErrorCode.ACCESS_DENIED, denyFailure.getErrorCode());

            assertEquals(ApprovalStatus.PENDING, request.getStatus());
            assertNull(request.getDecidedBy());
            assertNull(request.getDecidedAt());
        }
    }

    @Test
    void approvedRequestBindsTheExactRunOrderActionAndAmount() {
        ApprovalRequest request = refundApproval();
        request.approve(APPROVER, DECIDED_AT);

        assertTrue(request.binds("run-001", "order-001", AllowedAction.REFUND_ONLY, new BigDecimal("500.00")));
        assertFalse(request.binds("run-002", "order-001", AllowedAction.REFUND_ONLY, new BigDecimal("500.00")));
        assertFalse(request.binds("run-001", "order-002", AllowedAction.REFUND_ONLY, new BigDecimal("500.00")));
        assertFalse(request.binds("run-001", "order-001", AllowedAction.RETURN_REFUND, new BigDecimal("500.00")));
        assertFalse(request.binds("run-001", "order-001", AllowedAction.REFUND_ONLY, new BigDecimal("501.00")));
    }

    @Test
    void amountBindingUsesNumericEqualityInsteadOfBigDecimalScale() {
        ApprovalRequest request = refundApproval();

        assertTrue(request.binds("run-001", "order-001", AllowedAction.REFUND_ONLY, new BigDecimal("500.0")));
        assertTrue(request.binds("run-001", "order-001", AllowedAction.REFUND_ONLY, new BigDecimal("500.000")));
    }

    @Test
    void pureReturnBindingHasNoAmount() {
        ApprovalRequest request = ApprovalRequest.pending(
                "approval-002",
                "run-002",
                "order-002",
                "customer-001",
                AllowedAction.RETURN,
                null,
                "RETURN_WINDOW",
                "APPROVAL_REQUIRED_BY_POLICY",
                EXPIRES_AT);

        assertTrue(request.binds("run-002", "order-002", AllowedAction.RETURN, null));
        assertFalse(request.binds("run-002", "order-002", AllowedAction.RETURN, BigDecimal.ONE));
    }

    private static ApprovalRequest refundApproval() {
        return ApprovalRequest.pending(
                "approval-001",
                "run-001",
                "order-001",
                "customer-001",
                AllowedAction.REFUND_ONLY,
                new BigDecimal("500.00"),
                "HIGH_VALUE_REFUND",
                "APPROVAL_REQUIRED_BY_AMOUNT",
                EXPIRES_AT);
    }
}
