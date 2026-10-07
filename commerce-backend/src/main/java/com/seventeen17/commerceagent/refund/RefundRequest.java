package com.seventeen17.commerceagent.refund;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

/**
 * {@code commerce.refund_requests} —— 一笔逻辑退款。本项目里第一个代表"钱已经动了"的对象。
 *
 * <p>映射层的三个刻意选择：
 *
 * <ul>
 *   <li><b>只做持久化映射，不含任何授权逻辑。</b>金额上界、资格、幂等冲突都在
 *       {@link RefundService} 里以确定性方式判定；实体不提供任何 setter，V1 的行创建后不可变。
 *   <li><b>没有 {@code @Version}。</b>data-model 第 8 节没有为这张表定义乐观锁列，V1 也没有状态迁移，加一个
 *       没人读的版本号只会让"并发安全"看起来比实际更强。真正防重复的是 V003 的两个唯一约束。
 *   <li><b>{@code createdAt} / {@code updatedAt} 都标 {@code @Generated(INSERT)}。</b>取数据库时钟，两个字段因此
 *       不会出现跨时钟的先后倒置（T017 踩过 JVM 时钟与数据库时钟混用的坑）。V1 行不可变，所以 updated_at 暂时
 *       恒等于 created_at；将来允许状态迁移时，必须同时补上更新路径，否则这一列会停止说真话。
 * </ul>
 */
@Entity
@Table(name = "refund_requests")
public class RefundRequest {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    @Column(name = "order_id", length = 64, nullable = false, updatable = false)
    private String orderId;

    /** 退款归属，只来自服务端 principal；写入后不可变。 */
    @Column(name = "user_id", length = 64, nullable = false, updatable = false)
    private String userId;

    @Column(name = "reason_code", length = 100, nullable = false, updatable = false)
    private String reasonCode;

    @Column(name = "amount", precision = 19, scale = 2, nullable = false, updatable = false)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 32, nullable = false)
    private RefundStatus status;

    @Column(name = "idempotency_key", length = 128, nullable = false, updatable = false)
    private String idempotencyKey;

    /** 授权这笔退款的确定性规则（T020 的决策结果），用于回答"为什么付了这笔钱"。 */
    @Column(name = "eligibility_rule_code", length = 100, nullable = false, updatable = false)
    private String eligibilityRuleCode;

    /** V1 恒为 null：没有权威审批记录可绑定（US4/T049+）。 */
    @Column(name = "approval_request_id", length = 64, updatable = false)
    private String approvalRequestId;

    /** Agent run 关联，仅用于溯源；绝不用作身份或授权依据。 */
    @Column(name = "run_id", length = 64, nullable = false, updatable = false)
    private String runId;

    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    @Generated(event = EventType.INSERT)
    @Column(name = "updated_at", nullable = false, insertable = false, updatable = false)
    private Instant updatedAt;

    /** JPA 要求的无参构造器；业务代码请用下面的工厂方法。 */
    protected RefundRequest() {}

    public static RefundRequest create(
            String id,
            String orderId,
            String userId,
            String reasonCode,
            BigDecimal amount,
            String idempotencyKey,
            String eligibilityRuleCode,
            String approvalRequestId,
            String runId) {
        RefundRequest refund = new RefundRequest();
        refund.id = id;
        refund.orderId = orderId;
        refund.userId = userId;
        refund.reasonCode = reasonCode;
        refund.amount = amount;
        refund.status = RefundStatus.CREATED;
        refund.idempotencyKey = idempotencyKey;
        refund.eligibilityRuleCode = eligibilityRuleCode;
        refund.approvalRequestId = approvalRequestId;
        refund.runId = runId;
        return refund;
    }

    public String getId() {
        return id;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getUserId() {
        return userId;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public RefundStatus getStatus() {
        return status;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public String getEligibilityRuleCode() {
        return eligibilityRuleCode;
    }

    public String getApprovalRequestId() {
        return approvalRequestId;
    }

    public String getRunId() {
        return runId;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
