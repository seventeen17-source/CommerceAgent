package com.seventeen17.commerceagent.support;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Thin authenticated HTTP adapter; authorization and transaction live in the service. */
@RestController
@RequestMapping("/api/v1/support-tickets")
public class SupportTicketController {

    private final SupportTicketService service;

    public SupportTicketController(SupportTicketService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    SupportTicketResult create(
            @AuthenticationPrincipal CommercePrincipal principal,
            @Valid @RequestBody CreateSupportTicketRequest request) {
        return service.create(principal, request);
    }
}
