package com.seventeen17.commerceagent.order;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * T023: HTTP boundary for customer-scoped order reads.
 *
 * <p>The controller deliberately accepts no user id. Spring Security resolves the authenticated
 * {@link CommercePrincipal}; {@link OrderService} then scopes every read to that principal. The
 * controller stays thin so ownership, concealment and audit semantics cannot drift between HTTP
 * endpoints and internal callers.
 */
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    List<OrderSummary> listOwnOrders(@AuthenticationPrincipal CommercePrincipal principal) {
        return orderService.listOwnOrders(principal);
    }

    @GetMapping("/{orderId}")
    OrderSnapshot getOwnOrder(
            @AuthenticationPrincipal CommercePrincipal principal, @PathVariable String orderId) {
        return orderService.getOrder(principal, orderId);
    }
}
