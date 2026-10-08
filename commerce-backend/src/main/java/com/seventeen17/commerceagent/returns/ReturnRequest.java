package com.seventeen17.commerceagent.returns;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

/**
 * {@code commerce.return_requests} 的一行：US2 里"这件商品在走退货流程"这件事的落盘形式。
 *
 * <p>与 {@code RefundRequest} 刻意对称（V004 与 V003 同理）：字段名、不可变约定、时间戳的生成方式都一致，
 * 因此"同一逻辑请求只产生一行"这条性质在两张表上由同样两层约束保证 —— 用户维度的幂等键唯一，加上订单维度
 * 的<b>部分</b>唯一索引。
 *
 * <p>这里<b>没有金额列</b>，这是有意的：退货行表达的是"哪一单、走到哪一步、哪条规则批准的"，而"退多少钱"
 * 属于退款行（{@code commerce.refund_requests.amount}）。同一件事只留一个家，否则两个金额迟早会不一致。
 *
 * <p>V1 的行在创建后不可变（{@code status} 停在 {@link ReturnStatus#CREATED}），所以没有 {@code @Version}
 * 列 —— 加一个没人读的并发令牌就是死 schema。状态流转落地时，那次 migration 必须同时补上并发令牌并让
 * {@code updated_at} 保持新鲜。
 */
@Entity
@Table(name = "return_requests")
public class ReturnRequest {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    @Column(name = "order_id", length = 64, nullable = false, updatable = false)
    private String orderId;

    @Column(name = "user_id", length = 64, nullable = false, updatable = false)
    private String userId;

    @Column(name = "reason_code", length = 100, nullable = false, updatable = false)
    private String reasonCode;

    /**
     * T040：调用方声明的退货方式，可空，V1 不给它任何行为。
     *
     * <p>它落库的唯一理由是**参与幂等指纹**：一个决定"这是不是同一次逻辑请求"的字段，必须能与第一次尝试
     * 存下来的值比较，否则"同一个 key、换一种退货方式"就会被静默当成同一次写入。{@code reason_code} 落库
     * 是同一个理由。等退货处理真的给它语义时，那次改动负责定义取值集合 —— 这里刻意不发明词表。
     */
    @Column(name = "return_method", length = 32, updatable = false)
    private String returnMethod;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 32, nullable = false)
    private ReturnStatus status;

    @Column(name = "idempotency_key", length = 128, nullable = false, updatable = false)
    private String idempotencyKey;

    @Column(name = "eligibility_rule_code", length = 100, nullable = false, updatable = false)
    private String eligibilityRuleCode;

    /** 授权该高风险退货动作的权威审批引用；无需审批的退货为 null。 */
    @Column(name = "approval_request_id", length = 64, updatable = false)
    private String approvalRequestId;

    /** 不透明的 Agent run 关联 id：只用于追踪，<b>绝不用来授权</b>（跨服务、无法校验）。 */
    @Column(name = "run_id", length = 64, nullable = false, updatable = false)
    private String runId;

    /**
     * T040：受理这笔退货时冻结下来的退货截止时刻（规则窗口天数 + 运单签收时刻）。
     *
     * <p>它可空，且**可空是有意的**：契约把 {@code returnDeadline} 标为可空，而"决策只在窗口可算时才放行"
     * 已经由 T039 保证，所以 V1 写出来的行一定带值。可空留给将来"不带窗口的退货规则"，那种情况不该需要改表。
     *
     * <p>为什么不读时再算一遍：截止日是**对客户承诺过的事实**，规则改版或运单被重新播种都不该把它改写 ——
     * 与退款行冻结"实际接受的金额"是同一条理由。
     */
    @Column(name = "return_deadline", updatable = false)
    private Instant returnDeadline;

    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    @Generated(event = EventType.INSERT)
    @Column(name = "updated_at", nullable = false, insertable = false, updatable = false)
    private Instant updatedAt;

    protected ReturnRequest() {}

    /**
     * 工厂：只组装字段，不决定任何业务规则。
     *
     * <p>{@code status} 不是参数：新行永远是 {@link ReturnStatus#CREATED}，调用方无法从外面塞一个别的状态
     * 进来。与 {@code RefundRequest.create} 同样的取舍。
     */
    public static ReturnRequest create(
            String id,
            String orderId,
            String userId,
            String reasonCode,
            String returnMethod,
            String idempotencyKey,
            String eligibilityRuleCode,
            String approvalRequestId,
            String runId,
            Instant returnDeadline) {
        ReturnRequest request = new ReturnRequest();
        request.id = id;
        request.orderId = orderId;
        request.userId = userId;
        request.reasonCode = reasonCode;
        request.returnMethod = returnMethod;
        request.status = ReturnStatus.CREATED;
        request.idempotencyKey = idempotencyKey;
        request.eligibilityRuleCode = eligibilityRuleCode;
        request.approvalRequestId = approvalRequestId;
        request.runId = runId;
        request.returnDeadline = returnDeadline;
        return request;
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

    public String getReturnMethod() {
        return returnMethod;
    }

    public ReturnStatus getStatus() {
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

    public Instant getReturnDeadline() {
        return returnDeadline;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
