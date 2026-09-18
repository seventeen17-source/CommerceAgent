package com.seventeen17.commerceagent.common.error;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

@Component
public class SecurityErrorResponseWriter {

    private final JsonMapper jsonMapper;
    private final ErrorResponseFactory errorResponseFactory;

    public SecurityErrorResponseWriter(JsonMapper jsonMapper, ErrorResponseFactory errorResponseFactory) {
        this.jsonMapper = jsonMapper;
        this.errorResponseFactory = errorResponseFactory;
    }

    public void write(HttpServletRequest request, HttpServletResponse response, ErrorCode errorCode)
            throws IOException {
        ErrorResponse body = errorResponseFactory.create(request, errorCode);
        response.setStatus(errorCode.httpStatus());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader(TraceIdFilter.HEADER_NAME, body.traceId());
        jsonMapper.writeValue(response.getOutputStream(), body);
    }
}
