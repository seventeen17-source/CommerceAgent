package com.seventeen17.commerceagent.eligibility;

/**
 * 售后规则允许的权威动作。
 *
 * <p>取值必须与 V001 的 {@code chk_after_sales_rules_allowed_action} 完全一致。它不是模型建议集合，而是 Java
 * eligibility service 可返回的确定性业务动作。
 */
public enum AllowedAction {
    REFUND_ONLY,
    RETURN,
    RETURN_REFUND,
    MANUAL_REVIEW,
    DENY
}
