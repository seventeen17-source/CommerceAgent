package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.order.AfterSalesStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderItem;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.returns.ReturnRequest;
import com.seventeen17.commerceagent.returns.ReturnRequestRepository;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

/**
 * T038 — the two idempotency constraints, proven against a real PostgreSQL.
 *
 * <p>Both violations arrive as SQLState 23505, so the constraint <em>name</em> is the only thing that
 * separates "the caller retried with the same key" from "somebody is opening a second live return for
 * the same order". An assertion on "something failed" would pass even if the wrong constraint fired.
 *
 * <p>{@code @AfterEach} is load-bearing rather than tidiness: all three tests use the same order, so
 * without it the first test's live return decides the second test's outcome. That failure mode is
 * worth naming because it looks exactly like a broken implementation while actually being one test
 * inheriting another test's world.
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class ReturnIdempotencyIntegrationTest {

    private static final String OWNER_ID = "t038-owner";

    private static final String ORDER_ID = "T038-order-1";

    @Autowired
    private ReturnRequestRepository returnRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @AfterEach
    void removeT038Rows() {
        jdbcTemplate.update("DELETE FROM commerce.return_requests WHERE order_id = ?", ORDER_ID);
    }

    @Test
    void theSameLogicalRequestMayOnlyProduceOneRow() {
        seed();
        returnRepository.saveAndFlush(row("T038-ret-1", "key-1"));

        DataIntegrityViolationException thrown = assertThrows(
                DataIntegrityViolationException.class, () -> returnRepository.saveAndFlush(row("T038-ret-2", "key-1")));

        assertTrue(
                causeMessage(thrown).contains("uq_return_requests_user_idempotency_key"),
                "expected the idempotency-key constraint, got: " + causeMessage(thrown));
    }

    @Test
    void aSecondLiveReturnForTheSameOrderIsRejectedEvenWithADifferentKey() {
        seed();
        // A different key, so the retry guard above cannot be what stops this one.
        returnRepository.saveAndFlush(row("T038-ret-3", "key-3"));

        DataIntegrityViolationException thrown = assertThrows(
                DataIntegrityViolationException.class, () -> returnRepository.saveAndFlush(row("T038-ret-4", "key-4")));

        assertTrue(
                causeMessage(thrown).contains("uq_return_requests_order_id_active"),
                "expected the partial unique index, got: " + causeMessage(thrown));
    }

    @Test
    void aTerminalReturnDoesNotBlockALaterOne() {
        seed();
        returnRepository.saveAndFlush(row("T038-ret-5", "key-5"));
        // V1 rows are immutable through the entity (no setters), so a terminal status is reached the
        // way the future transition migration will have to: directly, in SQL.
        jdbcTemplate.update("UPDATE commerce.return_requests SET status = 'REJECTED' WHERE id = ?", "T038-ret-5");

        // The index is partial precisely so that this succeeds.
        ReturnRequest later = returnRepository.saveAndFlush(row("T038-ret-6", "key-6"));

        assertTrue(returnRepository.findById(later.getId()).isPresent());
    }

    private ReturnRequest row(String id, String idempotencyKey) {
        return ReturnRequest.create(
                id, ORDER_ID, OWNER_ID, "LOGISTICS_DELAY", idempotencyKey, "T038-RULE", null, "t038-run");
    }

    private static String causeMessage(Exception thrown) {
        Throwable cause = thrown.getCause() == null ? thrown : thrown.getCause();
        return String.valueOf(cause.getMessage());
    }

    private void seed() {
        if (userRepository.findById(OWNER_ID).isEmpty()) {
            userRepository.save(User.create(OWNER_ID, OWNER_ID + "-username", UserRole.CUSTOMER));
        }
        if (orderRepository.findById(ORDER_ID).isEmpty()) {
            Order order = Order.create(ORDER_ID, OWNER_ID, OrderStatus.DELIVERED, amount("120.00"), "USD");
            order.addItem(OrderItem.create(
                    ORDER_ID + "-item-1",
                    ORDER_ID + "-product-1",
                    "Test Product",
                    "T038-CATEGORY",
                    amount("120.00"),
                    1));
            order.setAfterSalesStatus(AfterSalesStatus.REFUND_REQUESTED);
            orderRepository.saveAndFlush(order);
        }
    }

    private static BigDecimal amount(String value) {
        return value == null ? null : new BigDecimal(value);
    }
}
