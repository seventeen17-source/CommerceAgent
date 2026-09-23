package com.seventeen17.commerceagent.eligibility;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * T025: HTTP boundary for the deterministic after-sales eligibility authority.
 *
 * <p>The request carries a reason code because the Agent contract has descriptive context, but the
 * controller intentionally does not let that text participate in the decision. Only the
 * authenticated principal and {@link EligibilityService}'s authoritative reads can affect the
 * returned {@link EligibilityDecision}.
 */
@RestController
@RequestMapping("/api/v1/after-sales")
public class EligibilityController {

    private final EligibilityService eligibilityService;

    public EligibilityController(EligibilityService eligibilityService) {
        this.eligibilityService = eligibilityService;
    }

    @PostMapping("/eligibility")
    EligibilityDecision evaluate(
            @AuthenticationPrincipal CommercePrincipal principal, @Valid @RequestBody EligibilityRequest request) {
        return eligibilityService.evaluate(principal, request.orderId());
    }
}
