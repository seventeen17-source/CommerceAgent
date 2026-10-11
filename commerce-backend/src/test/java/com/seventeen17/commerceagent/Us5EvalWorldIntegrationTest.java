package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.fixture.EvalFault;
import com.seventeen17.commerceagent.fixture.EvalFaultInjection;
import com.seventeen17.commerceagent.fixture.FixtureLoader;
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * T063-live: the two US5 eval worlds must be *reachable through the real HTTP boundary*.
 *
 * <p>Why this test exists rather than trusting the fixture code. US5's live gate is only meaningful
 * if a reset can build a world where the failure is real: Java answers {@code MANUAL_REVIEW} from its
 * own rule table, or the logistics dependency genuinely cannot be read. A fixture that seeds the
 * right rows but never arms the injection would produce a case that passes for the wrong reason --
 * and, worse, the in-process dataset would still be green, so nothing else would notice.
 *
 * <p>The reset is therefore driven over HTTP (the same endpoint the eval runner calls) and the
 * failure is observed over HTTP (the same endpoint the Agent calls). Between them sits the entire
 * production path: security filter chain, controller, exception handler, error envelope.
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class Us5EvalWorldIntegrationTest {

    private static final String ORDER_ID = "order-001";
    private static final String CUSTOMER_ID = "customer-001";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private EvalFaultInjection faults;

    /**
     * The injection is a singleton in the Spring context, so a test that leaves it armed would make
     * *another* test class see a failing dependency it never asked for. Disarming here is what keeps
     * the fault scoped to the world that requested it.
     */
    @AfterEach
    void disarmInjection() {
        faults.clear();
    }

    @Test
    void manualReviewWorldHasExactlyOneRuleThatAsksForAHuman() throws Exception {
        String token = customerToken();
        resetTo(token, FixtureLoader.MANUAL_REVIEW_CASE);

        // The world is writable -- the order exists, is SHIPPED, and has a stalled shipment -- so the
        // only reason no refund happens is the rule's own answer.
        assertEquals(1, count("SELECT COUNT(*) FROM commerce.orders WHERE id = '" + ORDER_ID + "'"));
        assertEquals(1, count("SELECT COUNT(*) FROM commerce.shipments WHERE order_id = '" + ORDER_ID + "'"));
        // Exactly one active rule: two matching rules would be a CONFLICTING_RULES refusal, i.e. a
        // different failure route that would make this case pass for the wrong reason.
        assertEquals(
                1,
                count("SELECT COUNT(*) FROM commerce.after_sales_rules WHERE active = TRUE"),
                "the manual-review world must not inherit another case's rules");

        mockMvc.perform(post("/api/v1/after-sales/eligibility")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"orderId\":\"" + ORDER_ID + "\",\"reasonCode\":\"LOGISTICS_STALLED\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.eligible").value(false))
                .andExpect(jsonPath("$.allowedAction").value("MANUAL_REVIEW"))
                .andExpect(jsonPath("$.reasonCodes[0]").value("RULE_ACTION_MANUAL_REVIEW"))
                .andExpect(jsonPath("$.maxRefundAmount").value((Object) null));
    }

    @Test
    void logisticsUnavailableWorldFailsTheDependencyWhileItsDataStaysHealthy() throws Exception {
        String token = customerToken();
        resetTo(token, FixtureLoader.LOGISTICS_UNAVAILABLE_CASE);

        // The distinction this case lives on: the *data* is present and the order is refundable.
        // Only the answer is missing. Seeding a missing shipment instead would silently turn this
        // into the data-absence world, whose error code is a different one.
        assertEquals(1, count("SELECT COUNT(*) FROM commerce.shipments WHERE order_id = '" + ORDER_ID + "'"));
        assertEquals(
                1,
                count("SELECT COUNT(*) FROM commerce.after_sales_rules WHERE rule_code = 'LOGISTICS_STALLED_REFUND'"));
        assertEquals(EvalFault.LOGISTICS_DEPENDENCY_UNAVAILABLE, faults.activeFault());

        mockMvc.perform(get("/api/v1/orders/" + ORDER_ID + "/logistics").header("Authorization", "Bearer " + token))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.errorCode").value("DEPENDENCY_UNAVAILABLE"))
                // retryable=true is what makes the Agent spend its retry budget before stopping: if
                // the envelope said "not retryable", a safe stop would be reached without ever
                // exercising the budget this scenario is about.
                .andExpect(jsonPath("$.retryable").value(true));
    }

    @Test
    void anUnrelatedCaseCannotInheritTheInjectedFault() throws Exception {
        String token = customerToken();
        resetTo(token, FixtureLoader.LOGISTICS_UNAVAILABLE_CASE);
        mockMvc.perform(get("/api/v1/orders/" + ORDER_ID + "/logistics").header("Authorization", "Bearer " + token))
                .andExpect(status().isServiceUnavailable());

        // Switching worlds must switch the failure off, or every later case would run against a
        // broken dependency and the eval would report model failures that are really fixture leaks.
        resetTo(token, "refund-logistics-001");

        assertEquals(EvalFault.NONE, faults.activeFault());
        mockMvc.perform(get("/api/v1/orders/" + ORDER_ID + "/logistics").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("IN_TRANSIT"))
                .andExpect(jsonPath("$.stalledHours").isNumber());
    }

    @Test
    void theFaultOnlyFailsTheWorldThatAskedForIt() throws Exception {
        String token = customerToken();
        resetTo(token, FixtureLoader.MANUAL_REVIEW_CASE);

        // A world with no injection still reads logistics normally; the interceptor is registered on
        // the path, so "registered" and "armed" have to be two different things.
        assertEquals(EvalFault.NONE, faults.activeFault());
        mockMvc.perform(get("/api/v1/orders/" + ORDER_ID + "/logistics").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk());
    }

    private void resetTo(String token, String caseId) throws Exception {
        mockMvc.perform(post("/internal/eval/fixtures/" + caseId + "/reset").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk());
    }

    /**
     * A token is only as usable as the user behind it.
     *
     * <p>{@code CommerceJwtAuthenticationConverter} resolves the token's {@code sub} against
     * {@code commerce.users} and refuses an unknown or inactive subject. So a test that mints a token
     * before the world exists gets {@code 401 AUTH_REQUIRED} from the reset endpoint itself -- the
     * reset is what seeds the user, which makes this a genuine ordering problem rather than a missing
     * header. Seeding the identity first is what breaks the cycle.
     */
    private String customerToken() {
        jdbcTemplate.update("""
                INSERT INTO commerce.users (id, username, role, status)
                VALUES ('customer-001', 'customer-001', 'CUSTOMER', 'ACTIVE')
                ON CONFLICT (id) DO UPDATE
                SET username = EXCLUDED.username,
                    role = EXCLUDED.role,
                    status = 'ACTIVE'
                """);
        return localJwtIssuer.issue(CUSTOMER_ID);
    }

    private long count(String sql) {
        Long value = jdbcTemplate.queryForObject(sql, Long.class);
        return value == null ? -1 : value;
    }
}
