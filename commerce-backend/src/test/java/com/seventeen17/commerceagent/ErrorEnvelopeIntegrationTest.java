package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.common.error.RestAccessDeniedHandler;
import com.seventeen17.commerceagent.common.error.TraceIdFilter;
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, ErrorProbeController.class})
@SpringBootTest
@AutoConfigureMockMvc
class ErrorEnvelopeIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

    @Autowired
    private RestAccessDeniedHandler accessDeniedHandler;

    @Test
    void unauthenticatedRequestUsesUnifiedErrorEnvelope() throws Exception {
        MvcResult result = mockMvc.perform(get("/__test/errors/business"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().exists(TraceIdFilter.HEADER_NAME))
                .andExpect(jsonPath("$.errorCode").value("AUTH_REQUIRED"))
                .andExpect(jsonPath("$.retryable").value(false))
                .andExpect(jsonPath("$.details").isMap())
                .andReturn();

        assertTraceIdMatchesHeader(result);
    }

    @Test
    void invalidBearerTokenUsesUnifiedErrorEnvelope() throws Exception {
        seedUser("t012-invalid-token");
        String token = localJwtIssuer.issue("t012-invalid-token");
        char replacement = token.charAt(token.length() - 1) == 'A' ? 'B' : 'A';
        String tampered = token.substring(0, token.length() - 1) + replacement;

        MvcResult result = mockMvc.perform(
                        get("/__test/errors/business").header("Authorization", "Bearer " + tampered))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("AUTH_REQUIRED"))
                .andReturn();

        assertTraceIdMatchesHeader(result);
    }

    @Test
    void businessExceptionUsesStableCodeAndHttpStatus() throws Exception {
        String token = tokenFor("t012-business");

        MvcResult result = mockMvc.perform(
                        get("/__test/errors/business").header("Authorization", "Bearer " + token))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("INVALID_ORDER_STATE"))
                .andExpect(jsonPath("$.message").value("Order state does not allow the requested action"))
                .andExpect(jsonPath("$.retryable").value(false))
                .andReturn();

        assertTraceIdMatchesHeader(result);
    }

    @Test
    void beanValidationUsesInvalidParameterEnvelope() throws Exception {
        String token = tokenFor("t012-validation");

        MvcResult result = mockMvc.perform(post("/__test/errors/validation")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.retryable").value(false))
                .andExpect(jsonPath("$.details.fieldErrors.value").value("value must not be blank"))
                .andReturn();

        assertTraceIdMatchesHeader(result);
    }

    @Test
    void unexpectedExceptionDoesNotLeakInternalMessage() throws Exception {
        String token = tokenFor("t012-internal");

        MvcResult result = mockMvc.perform(
                        get("/__test/errors/internal").header("Authorization", "Bearer " + token))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.errorCode").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.message").value("Internal server error"))
                .andReturn();

        String body = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertFalse(body.contains("sensitive-internal-message-must-not-leak"));
        assertTraceIdMatchesHeader(result);
    }

    @Test
    void accessDeniedHandlerUsesUnifiedErrorEnvelope() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        accessDeniedHandler.handle(request, response, new AccessDeniedException("denied"));

        assertTrue(response.getStatus() == 403);
        String traceId = response.getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(traceId);
        String body = response.getContentAsString(StandardCharsets.UTF_8);
        assertTrue(body.contains("\"errorCode\":\"ACCESS_DENIED\""));
        assertTrue(body.contains("\"retryable\":false"));
        assertTrue(body.contains("\"traceId\":\"" + traceId + "\""));
    }

    private String tokenFor(String userId) {
        seedUser(userId);
        return localJwtIssuer.issue(userId);
    }

    private void seedUser(String userId) {
        User user = User.create(userId, userId, UserRole.CUSTOMER);
        userRepository.saveAndFlush(user);
    }

    private void assertTraceIdMatchesHeader(MvcResult result) throws Exception {
        String traceId = result.getResponse().getHeader(TraceIdFilter.HEADER_NAME);
        assertNotNull(traceId);
        String body = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertTrue(body.contains("\"traceId\":\"" + traceId + "\""));
    }
}
