package com.seventeen17.commerceagent.approval;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;

/**
 * Capability guard for approval decisions.
 *
 * <p>Authentication and approval authority are deliberately separate facts. A valid CUSTOMER or
 * SUPPORT principal is authenticated but still has no right to approve a state-changing action.
 * The role comes from the authoritative Java principal, never from request JSON or model output.
 */
public final class ApprovalAuthorization {

    private ApprovalAuthorization() {}

    public static void requireApprover(CommercePrincipal principal) {
        if (principal == null) {
            throw new BusinessException(ErrorCode.AUTH_REQUIRED);
        }
        if (principal.role() != UserRole.APPROVER) {
            throw new BusinessException(
                    ErrorCode.ACCESS_DENIED, "Only an authorized approver may decide an approval request");
        }
    }
}
