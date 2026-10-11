package com.seventeen17.commerceagent.fixture;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * T063-live: which fault the currently reset eval world is carrying.
 *
 * <p>The constitution allows the eval fixture boundary to exist only under the {@code test} and
 * {@code eval} profiles, and a fault switch is part of that same boundary: it can make a production
 * dependency lie, so it must be impossible to enable in a production profile. The class-level
 * {@link Profile} annotation is what buys that -- not a property, which someone could set in a
 * deployed environment by accident.
 *
 * <p>State is deliberately a single volatile value rather than a per-request header or query
 * parameter. Two reasons: an injection that a *caller* could turn on by asking nicely would be a
 * remote "make this service fail" switch, and the eval world is a property of the world, not of the
 * request that happens to arrive next. Reset is the only thing that moves it.
 */
@Component
@Profile({"test", "eval"})
public class EvalFaultInjection {

    private final AtomicReference<EvalFault> active = new AtomicReference<>(EvalFault.NONE);

    /**
     * Point the injection at one case's world, or clear it for every other case.
     *
     * <p>Called *after* a successful reset, so the fault always belongs to the world that is
     * actually loaded. A reset that throws leaves the fault cleared (see {@link #clear()} being
     * called first by the controller) rather than leaving the previous world's fault in place.
     */
    public void applyForCase(String caseId) {
        active.set(
                FixtureLoader.LOGISTICS_UNAVAILABLE_CASE.equals(caseId)
                        ? EvalFault.LOGISTICS_DEPENDENCY_UNAVAILABLE
                        : EvalFault.NONE);
    }

    /** Return to the un-injected world. Called before every reset, including failing ones. */
    public void clear() {
        active.set(EvalFault.NONE);
    }

    public EvalFault activeFault() {
        return active.get();
    }

    public boolean logisticsUnavailable() {
        return active.get() == EvalFault.LOGISTICS_DEPENDENCY_UNAVAILABLE;
    }
}
