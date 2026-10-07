package com.seventeen17.commerceagent.eligibility;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * T020：确定性资格决策（契约 {@code EligibilityDecision}）。
 *
 * <p>它是**某一时刻、针对某个订单**的权威结论，不是"建议"。Agent 只能引用它，不能覆盖其中任何字段
 * （spec FR-010）；T026/T027 的写入路径在提交前必须重新校验一次，因为这里的结论会随着订单/物流/规则变化而
 * 过期（data-model："敏感写入前仍需重新校验"）。
 *
 * <p>这个 record 的紧凑构造器刻意不做"数据搬运"，而是**把契约里本来只是文字描述的字段关系变成不可违反的
 * 不变量**。原因是这些字段之间存在冗余（{@code eligible} 与 {@code allowedAction} 讲的是同一件事），
 * 冗余一旦只靠约定维系，就会漂移成"决策说 eligible=false，却同时给了一个可退金额"这种状态 —— 而下游把两者
 * 中的哪一个当真，决定的是钱：
 *
 * <ul>
 *   <li>{@code eligible} 必须与 {@code allowedAction} 一致：只有 {@code REFUND_ONLY} / {@code RETURN} /
 *       {@code RETURN_REFUND} 才算"批准了某个动作"，{@code DENY} / {@code MANUAL_REVIEW} 一律
 *       {@code eligible=false}；
 *   <li>未批准时**不得**携带 {@code maxRefundAmount}，也**不得**携带 {@code approvalRequired}：让一个被拒绝
 *       的决策仍带着金额，等于给下游留了一条"忽略 eligible 直接用金额"的路；
 *   <li>需要资金的动作用必须有金额（{@code REFUND_ONLY} / {@code RETURN_REFUND}），纯退货动作必须没有金额；
 *   <li>批准动作必须引用产生它的规则行（{@code ruleCode + ruleVersion}）；反过来，未选定规则时两者都为空
 *       —— 不允许只填一个；
 *   <li>**不批准**的决策至少要带一个 {@link EligibilityReasonCode}：拒绝必须能解释自己。已批准的决策允许
 *       {@code reasonCodes} 为空 —— 当规则没有声明任何条件时（无停滞阈值、无审批阈值），它的解释已经在
 *       {@code ruleCode + allowedAction + maxRefundAmount} 里；硬塞一个"条件已满足"的填充原因码只会变成
 *       Trace 与 Eval 里的噪声。
 * </ul>
 *
 * <p>T019 学到的教训在这里同样适用：**"不知道" ≠ "0"**。因此失败方向有两种而不是一种 —— 证据证明不符合走
 * {@code DENY}，证据不足以证明符合走 {@code MANUAL_REVIEW}，两者都不动钱，但对 Agent 的后续动作含义不同。
 */
public record EligibilityDecision(
        boolean eligible,
        AllowedAction allowedAction,
        BigDecimal maxRefundAmount,
        boolean approvalRequired,
        String ruleCode,
        Integer ruleVersion,
        List<EligibilityReasonCode> reasonCodes,
        Instant evaluatedAt) {

    public EligibilityDecision {
        Objects.requireNonNull(allowedAction, "allowedAction is required: a decision always names an action");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt is required: a decision is a statement about a moment");
        reasonCodes = List.copyOf(Objects.requireNonNull(reasonCodes, "reasonCodes is required"));
        if (!eligible && reasonCodes.isEmpty()) {
            throw new IllegalArgumentException("a decision that grants nothing must explain itself with a reason code");
        }
        if ((ruleCode == null) != (ruleVersion == null)) {
            throw new IllegalArgumentException("ruleCode and ruleVersion are cited together or not at all");
        }
        if (ruleVersion != null && ruleVersion < 1) {
            throw new IllegalArgumentException("ruleVersion must be a positive rule version");
        }

        // 正向列举而不是"排除 DENY/MANUAL_REVIEW"：将来 Java 新增一个动作取值时，默认必须是"没批准"，
        // 而不是因为没写进排除列表就自动变成已批准。
        boolean grantsAction = allowedAction == AllowedAction.REFUND_ONLY
                || allowedAction == AllowedAction.RETURN
                || allowedAction == AllowedAction.RETURN_REFUND;
        if (eligible != grantsAction) {
            throw new IllegalArgumentException(
                    "eligible and allowedAction disagree: eligible=" + eligible + " action=" + allowedAction);
        }
        if (!eligible && (maxRefundAmount != null || approvalRequired)) {
            throw new IllegalArgumentException("a decision that grants nothing cannot carry an amount or an approval");
        }
        if (eligible && ruleCode == null) {
            throw new IllegalArgumentException("a decision that grants an action must cite the rule it applied");
        }

        boolean movesMoney = allowedAction == AllowedAction.REFUND_ONLY || allowedAction == AllowedAction.RETURN_REFUND;
        if (movesMoney && eligible && maxRefundAmount == null) {
            throw new IllegalArgumentException("a money-granting decision must bound the amount it authorises");
        }
        if (!movesMoney && maxRefundAmount != null) {
            throw new IllegalArgumentException("only money-granting actions may carry a refund amount");
        }
        if (maxRefundAmount != null && maxRefundAmount.signum() < 0) {
            throw new IllegalArgumentException("maxRefundAmount cannot be negative");
        }
    }

    /** 本次决策是否解锁了一个会移动资金的动作；T027 只允许在这个为 {@code true} 时进入写入。 */
    public boolean grantsMoneyAction() {
        return eligible && (allowedAction == AllowedAction.REFUND_ONLY || allowedAction == AllowedAction.RETURN_REFUND);
    }
}
