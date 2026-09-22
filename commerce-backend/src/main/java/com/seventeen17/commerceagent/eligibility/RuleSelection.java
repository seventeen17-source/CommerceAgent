package com.seventeen17.commerceagent.eligibility;

/**
 * T020：规则选择的纯结果 —— "现在到底哪条规则管这个订单"。
 *
 * <p>把它单独建模，是因为"没选中规则"有三种**后果完全不同**的原因，合并成一个 {@code Optional.empty()}
 * 会让调用方只能回一句笼统的"不符合资格"：
 *
 * <ul>
 *   <li>{@link Status#NO_APPLICABLE_RULE} —— 规则集里根本没有这一类目；
 *   <li>{@link Status#ORDER_STATE_NOT_ELIGIBLE} —— 有这一类目的规则，但没有一条适用于订单当前状态
 *       （US2 的"已签收应走退货"就落在这一格）；
 *   <li>{@link Status#CONFLICTING_RULES} —— 两条以上不同 ruleCode 同时匹配，无法确定适用哪条政策。
 * </ul>
 *
 * <p>{@code rule != null} 与 {@code status == SELECTED} 必须同时成立或同时不成立：允许"选中了但状态是失败"
 * 这类组合存在，等于给调用方留了一个必须靠约定记住的判断。构造器直接把这种状态判为非法。
 */
record RuleSelection(AfterSalesRule rule, Status status) {

    enum Status {
        SELECTED,
        NO_APPLICABLE_RULE,
        ORDER_STATE_NOT_ELIGIBLE,
        CONFLICTING_RULES
    }

    RuleSelection {
        if ((rule == null) == (status == Status.SELECTED)) {
            throw new IllegalArgumentException("a selected rule and SELECTED status must always come together");
        }
    }

    static RuleSelection selected(AfterSalesRule rule) {
        return new RuleSelection(rule, Status.SELECTED);
    }

    static RuleSelection notSelected(Status status) {
        if (status == Status.SELECTED) {
            throw new IllegalArgumentException("use selected(rule) for a successful selection");
        }
        return new RuleSelection(null, status);
    }

    /**
     * 未选中时对应的原因码。
     *
     * <p>只有 {@code !isSelected()} 时才允许调用：已选中的选择没有"未解决原因"，静默返回 {@code null} 会让
     * 调用方把它塞进一个 {@code List.of(...)} 里，然后在很远的 NPE 处才暴露。这里直接失败。
     */
    EligibilityReasonCode unresolvedReason() {
        return switch (status) {
            case NO_APPLICABLE_RULE -> EligibilityReasonCode.NO_APPLICABLE_RULE;
            case ORDER_STATE_NOT_ELIGIBLE -> EligibilityReasonCode.ORDER_STATE_NOT_ELIGIBLE;
            case CONFLICTING_RULES -> EligibilityReasonCode.CONFLICTING_RULES;
            case SELECTED -> throw new IllegalStateException("a selected rule has no unresolved reason");
        };
    }

    boolean isSelected() {
        return status == Status.SELECTED;
    }
}
