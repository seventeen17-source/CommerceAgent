package com.seventeen17.commerceagent.approval;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.eligibility.EligibilityDecision;
import com.seventeen17.commerceagent.eligibility.EligibilityService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * T052: authoritative Approval create/list/decision service.
 *
 * <p>Three boundaries are deliberately separate:
 *
 * <ol>
 *   <li>Java eligibility decides whether a human is required and what action/amount is being
 *       proposed.
 *   <li>An APPROVER may accept or deny that exact proposal, but may not edit its binding.
 *   <li>The eventual refund/return write will re-read this row and re-check the binding again
 *       (T054); this service does not turn an id into a bearer token.
 * </ol>
 */
@Service
public class ApprovalService {

    /** Explicit V1 operational policy; business safety still comes from write-time revalidation. */
    static final Duration APPROVAL_TTL = Duration.ofHours(24);

    private static final String AUDIT_APPROVAL_REQUESTED = "APPROVAL_REQUESTED";
    private static final String AUDIT_APPROVAL_DECIDED = "APPROVAL_DECIDED";
    private static final String AUDIT_APPROVAL_EXPIRED = "APPROVAL_EXPIRED";

    private final ApprovalRequestRepository approvalRepository;
    private final EligibilityService eligibilityService;
    private final AuditWriter auditWriter;
    private final Clock clock;

    public ApprovalService(
            ApprovalRequestRepository approvalRepository,
            EligibilityService eligibilityService,
            AuditWriter auditWriter,
            Clock clock) {
        this.approvalRepository = approvalRepository;
        this.eligibilityService = eligibilityService;
        this.auditWriter = auditWriter;
        this.clock = clock;
    }

    @Transactional
    public ApprovalResult createApproval(CommercePrincipal principal, CreateApprovalRequest request) {
        requireCustomer(principal);

        EligibilityDecision decision = eligibilityService.evaluate(principal, request.orderId());
        String riskReason = requireExactApprovalProposal(request, decision);

        Instant now = clock.instant();
        Optional<ApprovalRequest> existing = approvalRepository.findByRunIdAndOrderIdAndActionAndStatus(
                request.runId().toString(),
                request.orderId(),
                request.actionType(),
                ApprovalStatus.PENDING);
        if (existing.isPresent() && !expireIfDue(existing.get(), now)) {
            return replayExisting(principal, request, decision, riskReason, existing.get());
        }
        ApprovalRequest approval = ApprovalRequest.pending(
                UUID.randomUUID().toString(),
                request.runId().toString(),
                request.orderId(),
                principal.userId(),
                request.actionType(),
                decision.maxRefundAmount(),
                decision.ruleCode(),
                riskReason,
                now.plus(APPROVAL_TTL));
        ApprovalRequest saved;
        try {
            saved = approvalRepository.saveAndFlush(approval);
        } catch (org.springframework.dao.DataIntegrityViolationException exception) {
            // V006's partial unique index is the final concurrency guard. We intentionally return a
            // stable conflict here rather than leaking a PostgreSQL 23505 as INTERNAL_ERROR. The
            // transaction is rolling back, so we do not try to query again inside it.
            throw new BusinessException(
                    ErrorCode.APPROVAL_CONFLICT,
                    "A live approval for this run/order/action was created concurrently",
                    exception);
        }

        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.USER,
                principal.userId(),
                AUDIT_APPROVAL_REQUESTED,
                "APPROVAL",
                saved.getId(),
                request.runId(),
                ApprovalStatus.PENDING.name(),
                auditMetadata(saved)));

        return ApprovalResult.from(saved);
    }

    @Transactional
    public ApprovalResult getOwnedApproval(CommercePrincipal principal, String approvalId) {
        requireCustomer(principal);
        ApprovalRequest approval = approvalRepository
                .findByIdAndUserIdForUpdate(approvalId, principal.userId())
                .orElseThrow(() -> new BusinessException(
                        ErrorCode.APPROVAL_NOT_FOUND,
                        "Approval request was not found or is not accessible to the authenticated user"));
        expireIfDue(approval, clock.instant());
        return ApprovalResult.from(approval);
    }

    @Transactional
    public List<ApprovalResult> listApprovals(CommercePrincipal principal, ApprovalStatus status) {
        ApprovalAuthorization.requireApprover(principal);

        // Expiry is materialized lazily at an authority read/decision boundary. Loading the whole
        // small V1 worklist first is intentional: otherwise status=EXPIRED would miss a row whose
        // deadline passed while its persisted status was still PENDING.
        List<ApprovalRequest> rows = approvalRepository.findAllByOrderByCreatedAtDesc();
        Instant now = clock.instant();
        for (ApprovalRequest row : rows) {
            expireIfDue(row, now);
        }
        return rows.stream()
                .filter(row -> status == null || row.getStatus() == status)
                .map(ApprovalResult::from)
                .toList();
    }

    @Transactional(noRollbackFor = BusinessException.class)
    public ApprovalResult decide(
            CommercePrincipal principal, String approvalId, ApprovalDecision decision) {
        ApprovalAuthorization.requireApprover(principal);
        ApprovalRequest approval = approvalRepository
                .findByIdForUpdate(approvalId)
                .orElseThrow(() -> new BusinessException(
                        ErrorCode.APPROVAL_NOT_FOUND, "Approval request was not found"));

        ApprovalStatus target =
                decision == ApprovalDecision.APPROVE ? ApprovalStatus.APPROVED : ApprovalStatus.DENIED;

        if (approval.getStatus() == target) {
            // A browser retry/double-click of the same decision is idempotent.
            return ApprovalResult.from(approval);
        }
        if (approval.getStatus() == ApprovalStatus.EXPIRED) {
            throw new BusinessException(ErrorCode.APPROVAL_EXPIRED);
        }
        if (approval.getStatus() != ApprovalStatus.PENDING) {
            throw new BusinessException(
                    ErrorCode.APPROVAL_CONFLICT,
                    "A terminal approval decision cannot be replaced by a different decision");
        }

        Instant now = clock.instant();
        if (expireIfDue(approval, now)) {
            // BusinessException is deliberately no-rollback for this method: the 409 tells the
            // caller the decision was refused while the EXPIRED transition remains an authoritative
            // fact instead of leaving a stale PENDING row behind.
            throw new BusinessException(
                    ErrorCode.APPROVAL_EXPIRED,
                    "The approval request has passed its expiresAt boundary and cannot be decided");
        }

        if (decision == ApprovalDecision.APPROVE) {
            approval.approve(principal, now);
        } else {
            approval.deny(principal, now);
        }
        ApprovalRequest saved = approvalRepository.saveAndFlush(approval);

        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.APPROVER,
                principal.userId(),
                AUDIT_APPROVAL_DECIDED,
                "APPROVAL",
                saved.getId(),
                UUID.fromString(saved.getRunId()),
                saved.getStatus().name(),
                auditMetadata(saved)));

        return ApprovalResult.from(saved);
    }

    private boolean expireIfDue(ApprovalRequest approval, Instant now) {
        if (approval.getStatus() != ApprovalStatus.PENDING || now.isBefore(approval.getExpiresAt())) {
            return false;
        }
        approval.expire(now);
        ApprovalRequest saved = approvalRepository.saveAndFlush(approval);
        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.SYSTEM,
                "commerce-backend",
                AUDIT_APPROVAL_EXPIRED,
                "APPROVAL",
                saved.getId(),
                UUID.fromString(saved.getRunId()),
                ApprovalStatus.EXPIRED.name(),
                auditMetadata(saved)));
        return true;
    }

    private static String requireExactApprovalProposal(
            CreateApprovalRequest request, EligibilityDecision decision) {
        if (!decision.eligible()) {
            if (decision.allowedAction() == AllowedAction.MANUAL_REVIEW) {
                throw new BusinessException(
                        ErrorCode.MANUAL_REVIEW_REQUIRED,
                        "Eligibility requires manual review rather than an approval request");
            }
            throw new BusinessException(
                    ErrorCode.ELIGIBILITY_DENIED,
                    "Deterministic eligibility does not authorize the proposed action");
        }
        if (!decision.approvalRequired()) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "Current authoritative eligibility does not require human approval");
        }
        if (request.actionType() != decision.allowedAction()) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "Approval action must exactly match the authoritative eligibility action");
        }
        if (!sameAmount(request.amount(), decision.maxRefundAmount())) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "Approval amount must exactly match the authoritative eligibility amount");
        }

        String authoritativeRiskReason = decision.reasonCodes().stream()
                .map(Enum::name)
                .filter(reason -> reason.startsWith("APPROVAL_"))
                .findFirst()
                .orElseThrow(() -> new BusinessException(
                        ErrorCode.INTERNAL_ERROR,
                        "approvalRequired=true without an authoritative approval reason"));
        if (!authoritativeRiskReason.equals(request.riskReason())) {
            throw new BusinessException(
                    ErrorCode.INVALID_PARAMETER,
                    "riskReason must match the authoritative approval reason");
        }
        return authoritativeRiskReason;
    }

    private static ApprovalResult replayExisting(
            CommercePrincipal principal,
            CreateApprovalRequest request,
            EligibilityDecision decision,
            String riskReason,
            ApprovalRequest existing) {
        boolean sameAmount = sameAmount(existing.getAmount(), decision.maxRefundAmount());
        boolean sameReason = existing.getReasonCode().equals(riskReason);
        boolean sameRule = existing.getEligibilityRuleCode().equals(decision.ruleCode());
        boolean sameUserFacingProposal = existing.getUserId().equals(principal.userId())
                && existing.getAction() == request.actionType()
                && existing.getRunId().equals(request.runId().toString())
                && existing.getOrderId().equals(request.orderId());

        if (!sameAmount || !sameReason || !sameRule || !sameUserFacingProposal) {
            throw new BusinessException(
                    ErrorCode.APPROVAL_CONFLICT,
                    "A live approval already exists for this run/order/action with a different binding");
        }
        return ApprovalResult.from(existing);
    }

    private static boolean sameAmount(BigDecimal left, BigDecimal right) {
        if (left == null || right == null) {
            return left == null && right == null;
        }
        return left.compareTo(right) == 0;
    }

    private static void requireCustomer(CommercePrincipal principal) {
        if (principal == null || principal.role() != UserRole.CUSTOMER) {
            throw new BusinessException(
                    ErrorCode.ACCESS_DENIED,
                    "Only the owning customer context may request approval for an after-sales action");
        }
    }

    private static Map<String, Object> auditMetadata(ApprovalRequest approval) {
        java.util.LinkedHashMap<String, Object> metadata = new java.util.LinkedHashMap<>();
        metadata.put("orderId", approval.getOrderId());
        metadata.put("action", approval.getAction().name());
        if (approval.getAmount() != null) {
            metadata.put("amount", approval.getAmount().toPlainString());
        }
        metadata.put("riskReason", approval.getReasonCode());
        metadata.put("ruleCode", approval.getEligibilityRuleCode());
        return Map.copyOf(metadata);
    }
}
