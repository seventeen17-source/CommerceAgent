package com.seventeen17.commerceagent.eligibility;

import com.seventeen17.commerceagent.order.OrderStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

/**
 * {@code commerce.after_sales_rules} —— Java eligibility service 使用的结构化、确定性业务规则。
 *
 * <p>这里的 {@code version} 是<b>业务规则版本</b>，不是 JPA 乐观锁版本，因此刻意不标注 {@code @Version}。
 * 同一 {@code ruleCode} 的多个历史版本通过数据库唯一约束 {@code (rule_code, version)} 共存。
 *
 * <p>T010 只负责持久化映射；“在某个时间点、某个订单/商品条件下应该命中哪条规则”的选择算法属于 T025。
 */
@Entity
@Table(name = "after_sales_rules")
public class AfterSalesRule {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false, updatable = false)
    private Long id;

    @Column(name = "rule_code", length = 100, nullable = false, updatable = false)
    private String ruleCode;

    /** 业务规则版本；由 uq_after_sales_rules_code_version 保证同一 ruleCode 下不重复。 */
    @Column(name = "version", nullable = false, updatable = false)
    private int version;

    @Column(name = "product_category", length = 100, updatable = false)
    private String productCategory;

    @Enumerated(EnumType.STRING)
    @Column(name = "required_order_status", length = 20, updatable = false)
    private OrderStatus requiredOrderStatus;

    @Column(name = "logistics_stalled_hours", updatable = false)
    private Integer logisticsStalledHours;

    @Column(name = "return_window_days", updatable = false)
    private Integer returnWindowDays;

    @Column(name = "max_refund_amount", precision = 19, scale = 2, updatable = false)
    private BigDecimal maxRefundAmount;

    @Column(name = "approval_threshold", precision = 19, scale = 2, updatable = false)
    private BigDecimal approvalThreshold;

    @Enumerated(EnumType.STRING)
    @Column(name = "allowed_action", length = 32, nullable = false, updatable = false)
    private AllowedAction allowedAction;

    @Column(name = "active", nullable = false)
    private boolean active;

    @Column(name = "effective_from", nullable = false, updatable = false)
    private Instant effectiveFrom;

    @Column(name = "effective_to", updatable = false)
    private Instant effectiveTo;

    protected AfterSalesRule() {}

    public static AfterSalesRule create(
            String ruleCode,
            int version,
            String productCategory,
            OrderStatus requiredOrderStatus,
            Integer logisticsStalledHours,
            Integer returnWindowDays,
            BigDecimal maxRefundAmount,
            BigDecimal approvalThreshold,
            AllowedAction allowedAction,
            boolean active,
            Instant effectiveFrom,
            Instant effectiveTo) {
        AfterSalesRule rule = new AfterSalesRule();
        rule.ruleCode = ruleCode;
        rule.version = version;
        rule.productCategory = productCategory;
        rule.requiredOrderStatus = requiredOrderStatus;
        rule.logisticsStalledHours = logisticsStalledHours;
        rule.returnWindowDays = returnWindowDays;
        rule.maxRefundAmount = maxRefundAmount;
        rule.approvalThreshold = approvalThreshold;
        rule.allowedAction = allowedAction;
        rule.active = active;
        rule.effectiveFrom = effectiveFrom;
        rule.effectiveTo = effectiveTo;
        return rule;
    }

    public Long getId() {
        return id;
    }

    public String getRuleCode() {
        return ruleCode;
    }

    public int getVersion() {
        return version;
    }

    public String getProductCategory() {
        return productCategory;
    }

    public OrderStatus getRequiredOrderStatus() {
        return requiredOrderStatus;
    }

    public Integer getLogisticsStalledHours() {
        return logisticsStalledHours;
    }

    public Integer getReturnWindowDays() {
        return returnWindowDays;
    }

    public BigDecimal getMaxRefundAmount() {
        return maxRefundAmount;
    }

    public BigDecimal getApprovalThreshold() {
        return approvalThreshold;
    }

    public AllowedAction getAllowedAction() {
        return allowedAction;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getEffectiveFrom() {
        return effectiveFrom;
    }

    public Instant getEffectiveTo() {
        return effectiveTo;
    }
}
