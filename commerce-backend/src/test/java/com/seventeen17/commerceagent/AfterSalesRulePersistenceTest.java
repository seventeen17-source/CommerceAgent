package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.eligibility.AfterSalesRule;
import com.seventeen17.commerceagent.eligibility.AfterSalesRuleRepository;
import com.seventeen17.commerceagent.eligibility.AllowedAction;
import com.seventeen17.commerceagent.order.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;
import org.hibernate.exception.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;

/** T010：验证 AfterSalesRule 的完整字段映射，以及业务规则版本唯一约束。 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class AfterSalesRulePersistenceTest {

    @Autowired
    private AfterSalesRuleRepository repository;

    @Test
    void persistsAndReadsStructuredRule() {
        Instant effectiveFrom = Instant.parse("2026-09-01T00:00:00Z");
        Instant effectiveTo = Instant.parse("2026-12-31T23:59:59Z");
        AfterSalesRule rule = AfterSalesRule.create(
                "T010-ROUNDTRIP",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                7,
                new BigDecimal("500.00"),
                new BigDecimal("300.00"),
                AllowedAction.REFUND_ONLY,
                true,
                effectiveFrom,
                effectiveTo);

        AfterSalesRule saved = repository.saveAndFlush(rule);
        assertNotNull(saved.getId());

        AfterSalesRule loaded = repository.findByRuleCodeAndVersion("T010-ROUNDTRIP", 1).orElseThrow();
        assertEquals("ELECTRONICS", loaded.getProductCategory());
        assertEquals(OrderStatus.SHIPPED, loaded.getRequiredOrderStatus());
        assertEquals(48, loaded.getLogisticsStalledHours());
        assertEquals(7, loaded.getReturnWindowDays());
        assertEquals(new BigDecimal("500.00"), loaded.getMaxRefundAmount());
        assertEquals(new BigDecimal("300.00"), loaded.getApprovalThreshold());
        assertEquals(AllowedAction.REFUND_ONLY, loaded.getAllowedAction());
        assertTrue(loaded.isActive());
        assertEquals(effectiveFrom, loaded.getEffectiveFrom());
        assertEquals(effectiveTo, loaded.getEffectiveTo());
    }

    @Test
    void duplicateRuleCodeAndBusinessVersionIsRejectedByNamedUniqueConstraint() {
        Instant effectiveFrom = Instant.parse("2026-09-01T00:00:00Z");
        AfterSalesRule first = AfterSalesRule.create(
                "T010-DUPLICATE",
                1,
                null,
                OrderStatus.SHIPPED,
                24,
                null,
                new BigDecimal("200.00"),
                null,
                AllowedAction.REFUND_ONLY,
                true,
                effectiveFrom,
                null);
        repository.saveAndFlush(first);

        AfterSalesRule duplicate = AfterSalesRule.create(
                "T010-DUPLICATE",
                1,
                "OTHER",
                OrderStatus.DELIVERED,
                null,
                7,
                null,
                null,
                AllowedAction.RETURN,
                true,
                effectiveFrom,
                null);

        DataIntegrityViolationException exception = assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(duplicate),
                "同一 rule_code + version 的第二条规则必须被数据库唯一约束拒绝");

        ConstraintViolationException constraintViolation = findConstraintViolation(exception);
        assertEquals("23505", constraintViolation.getSQLException().getSQLState(), "必须是 PostgreSQL unique_violation");
        assertEquals(
                "uq_after_sales_rules_code_version",
                constraintViolation.getConstraintName(),
                "必须由规则 code/version 唯一约束拒绝，而不是其他约束");
    }

    private static ConstraintViolationException findConstraintViolation(Throwable exception) {
        Throwable current = exception;
        while (current != null) {
            if (current instanceof ConstraintViolationException constraintViolation) {
                return constraintViolation;
            }
            current = current.getCause();
        }
        throw new AssertionError("异常链中没有 Hibernate ConstraintViolationException", exception);
    }
}
