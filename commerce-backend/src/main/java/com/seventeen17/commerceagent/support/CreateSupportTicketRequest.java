package com.seventeen17.commerceagent.support;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;

/** Client-supplied escalation facts, never the authenticated owner or ticket status. */
public record CreateSupportTicketRequest(
        @Size(max = 64) String orderId,
        @NotBlank @Size(max = 64) String category,

        @NotBlank @Size(max = 100) @Pattern(regexp = "^[A-Z0-9_:-]+$")
        String reasonCode,

        @NotBlank @Size(max = 2000) String evidenceSummary,
        @NotNull UUID runId) {}
