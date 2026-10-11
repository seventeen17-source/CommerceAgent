package com.seventeen17.commerceagent.fixture;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * T063-live: fails one read dependency at the HTTP boundary when the loaded eval world asks for it.
 *
 * <p><b>Why the web layer and not the service.</b> The honest place to make "logistics is
 * unavailable" observable is where the caller observes it. Throwing from here means the Agent faces
 * exactly what a real outage produces: the project's own error envelope, with the contract's status
 * code, error code and {@code retryable} flag, emitted by the same
 * {@code GlobalExceptionHandler} that emits it in production. Three alternatives were rejected:
 *
 * <ul>
 *   <li><b>Deleting the shipment row.</b> That is data absence, not a dependency failure; the
 *       repository already maps it to a different answer, so it would test the wrong branch.
 *   <li><b>Calling a fake URL from the Agent.</b> Then Java never handles a failure at all, so
 *       nothing about the Java-facing contract is verified -- and it would bypass ownership checks.
 *   <li><b>A fault flag inside {@code LogisticsService}.</b> That puts an eval-only branch in
 *       production code, where it can rot unnoticed because no production path runs it.
 * </ul>
 *
 * <p><b>What it deliberately cannot do.</b> It cannot be switched on by a request: the world decides,
 * not the caller. It cannot survive a reset of a different case (the controller clears it first). And
 * it cannot exist at all outside the {@code test}/{@code eval} profiles, so a deployed service has no
 * such bean to consult.
 */
@Component
@Profile({"test", "eval"})
class EvalFaultInterceptor implements HandlerInterceptor {

    private final EvalFaultInjection faults;

    EvalFaultInterceptor(EvalFaultInjection faults) {
        this.faults = faults;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (faults.logisticsUnavailable() && HttpMethod.GET.matches(request.getMethod())) {
            // DEPENDENCY_UNAVAILABLE, not LOGISTICS_UNAVAILABLE: the second one is what the
            // repository answers when the data is missing, and keeping the two apart is what lets a
            // reader tell "we could not reach a dependency" from "there is nothing to report".
            throw new BusinessException(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Injected eval fault: the logistics dependency is unavailable in this world");
        }
        return true;
    }
}
