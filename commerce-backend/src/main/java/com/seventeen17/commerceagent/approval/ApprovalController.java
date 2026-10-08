package com.seventeen17.commerceagent.approval;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** T052 HTTP boundary for authoritative human approvals. */
@RestController
@RequestMapping("/api/v1/approvals")
public class ApprovalController {

    private final ApprovalService approvalService;

    public ApprovalController(ApprovalService approvalService) {
        this.approvalService = approvalService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ApprovalResult create(
            @AuthenticationPrincipal CommercePrincipal principal,
            @Valid @RequestBody CreateApprovalRequest request) {
        return approvalService.createApproval(principal, request);
    }

    @GetMapping("/{approvalId}")
    ApprovalResult getOwned(
            @AuthenticationPrincipal CommercePrincipal principal,
            @PathVariable String approvalId) {
        return approvalService.getOwnedApproval(principal, approvalId);
    }

    @GetMapping
    List<ApprovalResult> list(
            @AuthenticationPrincipal CommercePrincipal principal,
            @RequestParam(required = false) ApprovalStatus status) {
        return approvalService.listApprovals(principal, status);
    }

    @PostMapping("/{approvalId}/decision")
    ApprovalResult decide(
            @AuthenticationPrincipal CommercePrincipal principal,
            @PathVariable String approvalId,
            @Valid @RequestBody ApprovalDecisionRequest request) {
        return approvalService.decide(principal, approvalId, request.decision());
    }
}
