package com.seventeen17.commerceagent.common.error;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Assigns exactly one correlation id per request and publishes it to MDC, the {@code X-Trace-Id}
 * response header and the unified error envelope.
 *
 * <p>An inbound {@code X-Trace-Id} is accepted only when it passes {@link #ACCEPTED_CORRELATION_ID}
 * format and length validation; anything else is replaced by a generated server trace id. The header
 * is caller-controlled text, and here it ends up in MDC (so on every log line of the request), in the
 * response header and in the persisted id that a failed Agent run is diagnosed by. Accepting it
 * unchecked would let a caller forge log lines and dictate the value our audit records are keyed on.
 *
 * <p>The Agent client sends {@code uuid4().hex} (32 lowercase hex chars), so a legitimate inbound id
 * survives validation and both services log the same id -- which is what makes cross-service diagnosis
 * possible at all.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Trace-Id";
    public static final String ATTRIBUTE_NAME = TraceIdFilter.class.getName() + ".traceId";

    /**
     * Format and length bound for an inbound correlation id, in one pattern. The character class
     * excludes CR, LF, whitespace, quotes and every control character; the {@code {8,128}} bound is
     * the length check and matches the Agent side's {@code max_length=128} column.
     */
    static final Pattern ACCEPTED_CORRELATION_ID = Pattern.compile("[A-Za-z0-9._-]{8,128}");

    private static final String MDC_KEY = "traceId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String traceId = currentOrCreate(request);
        response.setHeader(HEADER_NAME, traceId);
        MDC.put(MDC_KEY, traceId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY);
        }
    }

    /**
     * Returns this request's correlation id, resolving it once.
     *
     * <p>Resolution order is: already-resolved attribute, then a validated inbound header, then a
     * generated server id. The attribute check comes first so the header is consulted at most once per
     * request -- {@link com.seventeen17.commerceagent.common.error.ErrorResponseFactory} and
     * {@link com.seventeen17.commerceagent.common.error.GlobalExceptionHandler} call this again while
     * building an error body and must get the same id the filter logged. Storing the result on the
     * request also keeps one decision point for whether an inbound id may be trusted.
     */
    public static String currentOrCreate(HttpServletRequest request) {
        Object existing = request.getAttribute(ATTRIBUTE_NAME);
        if (existing instanceof String traceId && !traceId.isBlank()) {
            return traceId;
        }

        String traceId =
                acceptInboundCorrelationId(request.getHeader(HEADER_NAME)).orElseGet(TraceIdFilter::newServerTraceId);
        request.setAttribute(ATTRIBUTE_NAME, traceId);
        return traceId;
    }

    static Optional<String> acceptInboundCorrelationId(String candidate) {
        if (candidate == null || !ACCEPTED_CORRELATION_ID.matcher(candidate).matches()) {
            return Optional.empty();
        }
        return Optional.of(candidate);
    }

    private static String newServerTraceId() {
        return UUID.randomUUID().toString();
    }
}
