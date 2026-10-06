package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.returns.ReturnCommand;
import com.seventeen17.commerceagent.returns.ReturnResult;
import com.seventeen17.commerceagent.returns.ReturnService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * T040 service-level evidence for the two properties HTTP cannot show: "exactly one logical return" under
 * real concurrency, and the deadline being frozen at acceptance rather than derived again on every read.
 *
 * <p>Two real threads and a {@link CyclicBarrier} rather than an in-memory double: the thing being tested is
 * precisely the database's row lock plus the post-lock re-check, and a fake lock would only prove the fake
 * agrees with itself (the same reasoning T021 recorded for refunds).
 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, ReturnWriteIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
class ReturnWriteIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-10-06T08:00:00Z");
    private static final String OWNER_ID = "t040w-owner";
    private static final String ORDER_ID = "t040w-order";
    private static final String CATEGORY = "T040W_CATEGORY";
    private static final String RULE_CODE = "T040W-RETURN";
    private static final String RUN_ID = "33333333-4444-4555-8666-777777777777";
    private static final CommercePrincipal OWNER = new CommercePrincipal(OWNER_ID, UserRole.CUSTOMER);

    @Autowired
    private ReturnService returnService;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Autowired
    private AfterSalesRuleRepository ruleRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void concurrentReturnsWithDifferentKeysProduceExactlyOneReturn() throws Exception {
        seed();

        List<String> outcomes =
                runConcurrently(() -> attemptReturn("t040w_key_first"), () -> attemptReturn("t040w_key_second"));

        assertEquals(1, countReturns());
        assertTrue(outcomes.contains("refused:DUPLICATE_AFTER_SALES"), "输家必须拿到确定的业务错误，而不是 500 或第二行；实际=" + outcomes);
        assertEquals(
                1,
                outcomes.stream()
                        .filter(outcome -> !outcome.startsWith("refused"))
                        .count());
    }

    @Test
    void concurrentReturnsWithTheSameKeyProduceExactlyOneReturn() throws Exception {
        seed();

        List<String> outcomes =
                runConcurrently(() -> attemptReturn("t040w_key_same"), () -> attemptReturn("t040w_key_same"));

        assertEquals(1, countReturns());
        assertEquals(1, outcomes.stream().distinct().count(), "同一个 key 必须返回同一笔，实际=" + outcomes);
        assertFalse(outcomes.get(0).startsWith("refused"), "重放不是冲突；实际=" + outcomes);
    }

    @Test
    void theDeadlineIsFrozenAtAcceptanceAndDoesNotFollowALaterRuleRevision() throws Exception {
        seed();
        ReturnResult accepted = returnService.createReturn(
                OWNER, "t040w_key_frozen", new ReturnCommand(ORDER_ID, "DELIVERED_RETURN", null, null, RUN_ID));

        Instant acceptedDeadline = NOW.minus(Duration.ofDays(3)).plus(Duration.ofDays(7));
        assertEquals(acceptedDeadline, accepted.returnDeadline());

        // 规则改版：同一个 ruleCode 的新版本把窗口从 7 天放宽到 14 天。
        ruleRepository.saveAndFlush(AfterSalesRule.create(
                RULE_CODE,
                2,
                CATEGORY,
                OrderStatus.DELIVERED,
                null,
                14,
                new BigDecimal("500.00"),
                new BigDecimal("1000.00"),
                AllowedAction.RETURN,
                true,
                NOW.minus(Duration.ofDays(1)),
                null));

        // 已经承诺给客户的截止日不能跟着规则一起变 —— 这就是"存储而不是读时计算"的全部理由。
        List<ReturnResult> readBack = returnService.listReturns(OWNER, ORDER_ID);
        assertEquals(1, readBack.size());
        assertEquals(acceptedDeadline, readBack.get(0).returnDeadline());
        assertEquals(
                acceptedDeadline,
                jdbcTemplate
                        .queryForObject(
                                "SELECT return_deadline FROM commerce.return_requests WHERE order_id = ?",
                                Timestamp.class,
                                ORDER_ID)
                        .toInstant());
    }

    private String attemptReturn(String key) {
        try {
            return returnService
                    .createReturn(OWNER, key, new ReturnCommand(ORDER_ID, "DELIVERED_RETURN", null, null, RUN_ID))
                    .returnRequestId();
        } catch (BusinessException exception) {
            return "refused:" + exception.getErrorCode().name();
        }
    }

    private static List<String> runConcurrently(Callable<String> first, Callable<String> second) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CyclicBarrier barrier = new CyclicBarrier(2);
        try {
            List<Future<String>> futures = List.of(
                    pool.submit(() -> {
                        barrier.await(10, TimeUnit.SECONDS);
                        return first.call();
                    }),
                    pool.submit(() -> {
                        barrier.await(10, TimeUnit.SECONDS);
                        return second.call();
                    }));
            List<String> outcomes = new ArrayList<>();
            for (Future<String> future : futures) {
                outcomes.add(future.get(30, TimeUnit.SECONDS));
            }
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }

    private int countReturns() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM commerce.return_requests WHERE order_id = ?", Integer.class, ORDER_ID);
        return count == null ? 0 : count;
    }

    private void seed() {
        if (userRepository.findById(OWNER_ID).isEmpty()) {
            userRepository.saveAndFlush(User.create(OWNER_ID, OWNER_ID, UserRole.CUSTOMER));
        }
        if (orderRepository.findById(ORDER_ID).isEmpty()) {
            Order order = Order.create(ORDER_ID, OWNER_ID, OrderStatus.DELIVERED, new BigDecimal("120.00"), "USD");
            order.addItem(OrderItem.create(
                    ORDER_ID + "-item", ORDER_ID + "-product", "T040W Product", CATEGORY, new BigDecimal("120.00"), 1));
            orderRepository.saveAndFlush(order);
        }
        if (shipmentRepository.findById(ORDER_ID + "-shipment").isEmpty()) {
            Shipment shipment = Shipment.create(
                    ORDER_ID + "-shipment", ORDER_ID, "T040W", ORDER_ID + "-tracking", ShipmentStatus.DELIVERED);
            shipment.setSignedAt(NOW.minus(Duration.ofDays(3)));
            shipmentRepository.saveAndFlush(shipment);
        }
        if (ruleRepository.findByRuleCodeAndVersion(RULE_CODE, 1).isEmpty()) {
            ruleRepository.saveAndFlush(AfterSalesRule.create(
                    RULE_CODE,
                    1,
                    CATEGORY,
                    OrderStatus.DELIVERED,
                    null,
                    7,
                    new BigDecimal("500.00"),
                    new BigDecimal("1000.00"),
                    AllowedAction.RETURN,
                    true,
                    NOW.minus(Duration.ofDays(30)),
                    null));
        }
    }

    @AfterEach
    void removeT040wRows() {
        jdbcTemplate.update(
                "DELETE FROM commerce.audit_logs WHERE resource_type = 'RETURN' AND resource_id IN "
                        + "(SELECT id FROM commerce.return_requests WHERE order_id = ?)",
                ORDER_ID);
        jdbcTemplate.update("DELETE FROM commerce.return_requests WHERE order_id = ?", ORDER_ID);
        jdbcTemplate.update("DELETE FROM commerce.logistics_events WHERE shipment_id LIKE 't040w-%'");
        jdbcTemplate.update("DELETE FROM commerce.shipments WHERE id LIKE 't040w-%'");
        jdbcTemplate.update("DELETE FROM commerce.order_items WHERE order_id = ?", ORDER_ID);
        jdbcTemplate.update("DELETE FROM commerce.orders WHERE id = ?", ORDER_ID);
        jdbcTemplate.update("DELETE FROM commerce.after_sales_rules WHERE rule_code = ?", RULE_CODE);
        jdbcTemplate.update("DELETE FROM commerce.users WHERE id = ?", OWNER_ID);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
