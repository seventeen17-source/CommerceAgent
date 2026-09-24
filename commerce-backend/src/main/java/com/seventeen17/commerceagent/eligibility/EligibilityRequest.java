package com.seventeen17.commerceagent.eligibility;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * T025 HTTP request for deterministic eligibility evaluation.
 *
 * <p>{@code reasonCode} is descriptive context only. It is deliberately not forwarded into
 * {@link EligibilityService}: user/model wording must never select a rule, widen an amount or
 * unlock an action. The authoritative inputs remain the authenticated principal plus Java-owned
 * order, logistics and rule facts.
 */
public record EligibilityRequest(
        @NotBlank @Size(max = 64) String orderId,
        @NotBlank @Size(max = 100) String reasonCode) {}
