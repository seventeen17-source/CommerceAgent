package com.seventeen17.commerceagent.eligibility;

/**
 * T020：确定性资格决策的机器可读原因码，对应契约 {@code EligibilityDecision.reasonCodes}。
 *
 * <p>它回答的是"为什么是这个结论"，而 {@code errorCode} 回答的是"这次调用为什么没成功"。两者不是同一件事：
 * 一个 {@code eligible=false} 的拒绝是**成功的评估**，因此它以 200 决策 + 原因码表达，而不是错误响应；只有
 * "评估无法完成"（越权、依赖不可用、参数非法）才是错误。完整判据见 {@code contracts/error-contracts.md}。
 *
 * <p>取值被刻意分成三段，{@link EligibilityDecision} 的构造器据此约束结论与原因不能互相矛盾：
 *
 * <ul>
 *   <li><b>证据段</b>：{@link #STALL_THRESHOLD_MET} / {@link #STALL_THRESHOLD_NOT_MET} /
 *       {@link #LOGISTICS_EVIDENCE_UNAVAILABLE} / {@link #LOGISTICS_CONFLICTS_WITH_ORDER}；
 *   <li><b>金额段</b>：{@link #APPROVAL_REQUIRED_BY_AMOUNT} / {@link #AMOUNT_EXCEEDS_RULE_LIMIT}；
 *   <li><b>规则段</b>：{@link #NO_APPLICABLE_RULE} / {@link #ORDER_STATE_NOT_ELIGIBLE} /
 *       {@link #CONFLICTING_RULES} / {@link #RULE_ACTION_DENY} / {@link #RULE_ACTION_MANUAL_REVIEW} /
 *       {@link #RULE_ACTION_NOT_SUPPORTED} / {@link #ORDER_ALREADY_HAS_AFTER_SALES}。
 * </ul>
 *
 * <p>这些值会进入 Trace 与 Eval failure taxonomy，因此改名等于改对外可查询的事实，不能为了措辞好看而重命名。
 */
public enum EligibilityReasonCode {
    /** 物流停滞时长已达到规则阈值（阈值比较取等号）。 */
    STALL_THRESHOLD_MET,
    /** 物流停滞时长未达到规则阈值：结论是"证明不符合"，不是"无法判定"。 */
    STALL_THRESHOLD_NOT_MET,
    /** 规则要求停滞证据，但没有任何权威物流事件 —— "不知道"，因此转人工而不是拒绝。 */
    LOGISTICS_EVIDENCE_UNAVAILABLE,
    /** 订单状态与运单状态互相矛盾（例如订单 SHIPPED、运单已签收）：两个权威来源冲突时不猜。 */
    LOGISTICS_CONFLICTS_WITH_ORDER,
    /** 退款金额达到规则的审批阈值，资格允许但必须先取得权威审批。 */
    APPROVAL_REQUIRED_BY_AMOUNT,
    /** 订单金额超过规则允许的最大退款额：这是规则的硬边界，不接受部分退款兜底（V1 只支持整单退款）。 */
    AMOUNT_EXCEEDS_RULE_LIMIT,
    /** 该订单已存在售后动作，禁止再产生第二个逻辑售后对象。 */
    ORDER_ALREADY_HAS_AFTER_SALES,
    /** 规则集中没有任何一条适用于该订单（类目/状态都无从匹配）。 */
    NO_APPLICABLE_RULE,
    /** 该品类有规则，但没有一条适用于订单**当前**状态（例如只有 SHIPPED 规则而来的是 DELIVERED）。 */
    ORDER_STATE_NOT_ELIGIBLE,
    /** 两条以上不同的 ruleCode 同时匹配同一订单：无法确定适用哪条政策，转人工而不是任选一条。 */
    CONFLICTING_RULES,
    /** 规则本身要求的动作就是拒绝。 */
    RULE_ACTION_DENY,
    /** 规则本身要求的动作就是人工复核。 */
    RULE_ACTION_MANUAL_REVIEW,
    /** 规则要求的动作（退货类）在本版本没有可执行的证据校验，因此 fail closed 为人工复核。 */
    RULE_ACTION_NOT_SUPPORTED
}
