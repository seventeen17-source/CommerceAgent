package com.seventeen17.commerceagent.fixture;

/**
 * T063-live: the dependency failures an eval world is allowed to inject.
 *
 * <p>An eval case that claims "the Agent stays safe when a dependency fails" needs a world where the
 * dependency actually fails. Until now there was no such world: every fixture seeded *healthy* data,
 * and the only failure injection in the repository lived in Python tests as a scripted Tool double.
 * A scripted double proves the routing table is right; it cannot prove that the real contract
 * boundary (HTTP status, error envelope, retryable flag) reaches the Agent in the shape the routing
 * table expects.
 *
 * <p>The list is an enum rather than a free string on purpose: a fault name that no interceptor
 * understands would otherwise be accepted by the fixture and silently inject nothing -- a case that
 * cannot fail, which is the exact shape this project keeps hunting for.
 */
public enum EvalFault {
    /** No injection. The world behaves like every pre-T063 fixture world. */
    NONE,

    /**
     * The logistics read dependency is unavailable.
     *
     * <p>Deliberately injected at the HTTP boundary rather than by deleting the shipment row. The
     * two are different facts and only one of them is this scenario: a missing row is *data absence*
     * (the repository maps it to {@code LOGISTICS_UNAVAILABLE}), while an unavailable dependency is
     * "the answer could not be obtained". US5's first acceptance scenario is about the latter, so
     * the injection happens where a real dependency failure would surface -- the web layer -- and the
     * seeded data stays healthy and writable, so "nothing was refunded" is evidence of the Agent's
     * refusal rather than of an impossible world.
     */
    LOGISTICS_DEPENDENCY_UNAVAILABLE
}
