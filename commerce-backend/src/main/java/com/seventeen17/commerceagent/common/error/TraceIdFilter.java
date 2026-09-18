package com.seventeen17.commerceagent.common.error;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Trace-Id";
    public static final String ATTRIBUTE_NAME = TraceIdFilter.class.getName() + ".traceId";
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

    public static String currentOrCreate(HttpServletRequest request) {
        Object existing = request.getAttribute(ATTRIBUTE_NAME);
        if (existing instanceof String traceId && !traceId.isBlank()) {
            return traceId;
        }

        String traceId = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE_NAME, traceId);
        return traceId;
    }
}
