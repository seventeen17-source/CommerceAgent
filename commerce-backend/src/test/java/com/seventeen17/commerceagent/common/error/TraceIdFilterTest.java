package com.seventeen17.commerceagent.common.error;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.servlet.FilterChain;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/**
 * Unit tests for the tightened inbound correlation-id rule required by T016.
 *
 * <p>These run without a Spring context on purpose: the behaviour under test is a pure decision about
 * a request header, and pinning it in a fast test is what stops the validation from being quietly
 * dropped later.
 */
class TraceIdFilterTest {

    private final TraceIdFilter filter = new TraceIdFilter();

    @ParameterizedTest
    @ValueSource(
            strings = {
                // What the Python Agent client actually sends: uuid4().hex.
                "3f2b8c1d9e4a4b7c8d5e6f708192a3b4",
                // A generated server id must also be acceptable, so a proxied id round-trips.
                "b1e5f0a2-6c3d-4e7f-9a1b-2c3d4e5f6a7b",
                "trace.2026-09_19",
                "abcdefgh",
            })
    void validInboundCorrelationIdIsAcceptedAndReflected(String inbound) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, inbound);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> mdcDuringChain = new AtomicReference<>();

        filter.doFilter(request, response, captureMdc(mdcDuringChain));

        // One id space across both services: what we logged is what the caller can search for.
        assertEquals(inbound, response.getHeader(TraceIdFilter.HEADER_NAME));
        assertEquals(inbound, mdcDuringChain.get());
        assertEquals(inbound, request.getAttribute(TraceIdFilter.ATTRIBUTE_NAME));
    }

    @Test
    void missingInboundHeaderGeneratesAServerTraceId() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, captureMdc(new AtomicReference<>()));

        String reflected = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(reflected);
        // The generated form is a UUID string, not the compact hex the client sends.
        assertEquals(UUID.fromString(reflected).toString(), reflected);
    }

    @Test
    void blankInboundHeaderIsReplacedByAServerTraceId() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, "   ");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, captureMdc(new AtomicReference<>()));

        String reflected = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(reflected);
        assertTrue(TraceIdFilter.ACCEPTED_CORRELATION_ID.matcher(reflected).matches());
    }

    @Test
    void crlfInjectionCannotForgeALogLine() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, "evil\r\nX-Injected: yes");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> mdcDuringChain = new AtomicReference<>();

        filter.doFilter(request, response, captureMdc(mdcDuringChain));

        String reflected = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(reflected);
        assertNotEquals("evil\r\nX-Injected: yes", reflected);
        assertTrue(reflected.indexOf('\r') < 0);
        assertTrue(reflected.indexOf('\n') < 0);
        assertNotNull(mdcDuringChain.get());
        assertTrue(mdcDuringChain.get().indexOf('\n') < 0);
        // A rejected inbound id must still leave the request correlated, not uncorrelated.
        assertEquals(reflected, mdcDuringChain.get());
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "short",
                "has space",
                "quote\"inside",
                "tab\tinside",
                "unicode-\u00e9\u00e8",
            })
    void correlationIdOutsideTheFormatIsReplaced(String inbound) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, inbound);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, captureMdc(new AtomicReference<>()));

        String reflected = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(reflected);
        assertNotEquals(inbound, reflected);
        assertTrue(TraceIdFilter.ACCEPTED_CORRELATION_ID.matcher(reflected).matches());
    }

    /**
     * The length bound is a real boundary, not a decorative maximum: 128 chars is the Agent side's
     * {@code trace_id} column width, so an over-long id must be replaced rather than truncated or
     * stored. Built at runtime because annotation values have to be compile-time constants.
     */
    @Test
    void correlationIdLengthBoundIsEnforcedOnBothSides() throws Exception {
        assertEquals("0123456789abcdef".repeat(8), reflectedFor("0123456789abcdef".repeat(8)));
        assertNotEquals("0123456789abcdef".repeat(8) + "z", reflectedFor("0123456789abcdef".repeat(8) + "z"));
    }

    private String reflectedFor(String inbound) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, inbound);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, captureMdc(new AtomicReference<>()));

        String reflected = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(reflected);
        assertTrue(TraceIdFilter.ACCEPTED_CORRELATION_ID.matcher(reflected).matches());
        return reflected;
    }

    @Test
    void theIdIsResolvedOnceSoTheErrorEnvelopeCannotDriftFromTheLoggedId() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER_NAME, "aaaaaaaa-bbbb-cccc");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> mdcDuringChain = new AtomicReference<>();

        filter.doFilter(request, response, captureMdc(mdcDuringChain));

        // ErrorResponseFactory / GlobalExceptionHandler call currentOrCreate again while building an
        // error body; they must get the id the filter already logged, not a second one.
        String again = TraceIdFilter.currentOrCreate(request);
        assertEquals(mdcDuringChain.get(), again);
        assertEquals(response.getHeader(TraceIdFilter.HEADER_NAME), again);
    }

    @Test
    void mdcIsClearedAfterTheRequest() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, captureMdc(new AtomicReference<>()));

        assertNull(MDC.get("traceId"));
    }

    private static FilterChain captureMdc(AtomicReference<String> sink) {
        return (servletRequest, servletResponse) -> sink.set(MDC.get("traceId"));
    }
}
