package com.seventeen17.commerceagent.logistics;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * T024: HTTP boundary for customer-scoped authoritative logistics reads.
 *
 * <p>The controller deliberately accepts no user id and performs no stall calculation itself.
 * Spring Security supplies the authenticated {@link CommercePrincipal}; {@link LogisticsService}
 * enforces order ownership before reading shipment data; {@link LogisticsStallCalculator} owns the
 * deterministic derived facts. Keeping this boundary thin prevents HTTP callers or the Agent from
 * redefining what "stalled" means.
 */
@RestController
@RequestMapping("/api/v1/orders")
public class LogisticsController {

    private final LogisticsService logisticsService;

    public LogisticsController(LogisticsService logisticsService) {
        this.logisticsService = logisticsService;
    }

    @GetMapping("/{orderId}/logistics")
    LogisticsSnapshot getLogistics(
            @AuthenticationPrincipal CommercePrincipal principal, @PathVariable String orderId) {
        return logisticsService.getLogistics(principal, orderId);
    }
}
