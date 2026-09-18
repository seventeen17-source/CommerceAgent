package com.seventeen17.commerceagent.security;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Exposes the authoritative principal resolved by Spring Security.
 *
 * <p>The caller supplies only the Bearer token. userId/role come from the verified JWT subject plus
 * the current commerce.users record resolved by {@link CommerceJwtAuthenticationConverter}; request
 * or model text can never override either field.
 */
@RestController
@RequestMapping("/api/v1")
public class CurrentPrincipalController {

    @GetMapping("/me")
    CurrentPrincipalResponse current(@AuthenticationPrincipal CommercePrincipal principal) {
        return new CurrentPrincipalResponse(principal.userId(), principal.role());
    }
}
