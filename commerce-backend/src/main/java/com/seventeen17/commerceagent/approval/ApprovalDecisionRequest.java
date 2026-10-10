package com.seventeen17.commerceagent.approval;

import jakarta.validation.constraints.NotNull;

/** Request body for an authorized human decision. */
public record ApprovalDecisionRequest(@NotNull ApprovalDecision decision) {}
