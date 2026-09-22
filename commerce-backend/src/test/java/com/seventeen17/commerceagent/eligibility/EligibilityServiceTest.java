package com.seventeen17.commerceagent.eligibility;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.logistics.LogisticsSnapshot;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.AfterSalesStatus;
import com.seventeen17.commerceagent.order.OrderSnapshot;
import com.seventeen17.commerceagent.order.OrderStatus;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * T020：deterministic eligibility 与"拒绝模型"的可执行规格。
 *
 * <p>这个测试**不启动 Spring、不连数据库**，因为被验证的 {@link EligibilityService#selectRule} /
 * {@link EligibilityService#decide} 是纯函数：所有输入（订单事实、规则行、物流事实、当前时刻）都由参数传入。
 * "没有随机数、没有真实时钟、没有隐藏状态"因此不是一句承诺 —— 它在类型上就无法从别处取值。
 *
 * <p>被钉死的是三组东西：
 *
 * <h2>1. 规则选择是确定性的</h2>
 *
 * 类目通配（{@code product_category = null}）、状态通配、生效窗口（半开区间）、版本共存（同一 ruleCode 取最新
 * 版本）、以及"两个不同 ruleCode 同时匹配"必须转人工而不是任选一条。最后一条尤其重要：任选一条等于让 seed 数据
 * 的插入顺序决定用户能退多少钱（见
 * {@link #oneOrderMatchingTwoDistinctRuleCodesCannotBeDecidedAutomatically()}）。
 *
 * <h2>2. 金额只能来自权威事实，而且只能是更少的钱</h2>
 *
 * 可退金额取订单总额，规则上限是硬边界；审批阈值取等号；规则没有上限时也不会变成"无上限"。
 *
 * <h2>3. "证明不符合"与"无法证明符合"是两种结论</h2>
 *
 * 停滞不够 → {@code DENY}；停滞时长未知 → {@code MANUAL_REVIEW}。两者都不动钱，但后者要转人工（US5），把它
 * 写成 {@code DENY} 会让"证据不足"看起来像"业务上明确拒绝"，US5 的人工升级路径就失去了触发依据。
 *
 * <p>另外，{@link EligibilityDecision} 的构造器本身就是被测对象之一：契约里
 * {@code eligible} 与 {@code allowedAction} 是冗余字段，这个测试要求"互相矛盾的决策根本无法被构造出来"
 * （见 {@link #decisionsThatContradictThemselvesCannotBeConstructed()}）。
 */
class EligibilityServiceTest {

    /** 固定的"现在"。业务代码的时间来自注入的 Clock，纯函数直接收参数，因此这里可以精确断言生效窗口。 */
    private static final Instant NOW = Instant.parse("2026-09-20T08:00:00Z");

    private static final Instant EFFECTIVE_FROM = Instant.parse("2026-09-01T00:00:00Z");

    // ------------------------------------------------------------------
    // 规则选择
    // ------------------------------------------------------------------

    @Test
    void selectsTheRuleThatMatchesCategoryAndCurrentOrderStatus() {
        AfterSalesRule electronics = refundRule("T020-ELECTRONICS", 1, "ELECTRONICS", OrderStatus.SHIPPED);
        AfterSalesRule home = refundRule("T020-HOME", 1, "HOME", OrderStatus.SHIPPED);

        RuleSelection selection =
                EligibilityService.selectRule(shippedOrder("199.00"), List.of(electronics, home), NOW);

        assertTrue(selection.isSelected());
        assertEquals("T020-ELECTRONICS", selection.rule().getRuleCode());
    }

    @Test
    void inactiveRulesAreIgnored() {
        AfterSalesRule disabled = rule(
                "T020-DISABLED",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                "500.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                false,
                EFFECTIVE_FROM,
                null);

        RuleSelection selection = EligibilityService.selectRule(shippedOrder("199.00"), List.of(disabled), NOW);

        assertEquals(RuleSelection.Status.NO_APPLICABLE_RULE, selection.status());
    }

    @Test
    void rulesOutsideTheirEffectiveWindowNeverApply() {
        OrderSnapshot order = shippedOrder("199.00");
        // effectiveTo 是开区间端点：正好等于 now 时这条规则已经不再生效。
        AfterSalesRule expired = rule(
                "T020-EXPIRED",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                "500.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                NOW);
        AfterSalesRule notYetEffective = rule(
                "T020-FUTURE",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                "500.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                true,
                NOW.plus(Duration.ofDays(1)),
                null);

        assertEquals(
                RuleSelection.Status.NO_APPLICABLE_RULE,
                EligibilityService.selectRule(order, List.of(expired), NOW).status());
        assertEquals(
                RuleSelection.Status.NO_APPLICABLE_RULE,
                EligibilityService.selectRule(order, List.of(notYetEffective), NOW)
                        .status());
    }

    @Test
    void newestVersionWinsWhenSeveralVersionsOfOneRuleAreActive() {
        AfterSalesRule older = rule(
                "T020-VERSIONED",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                "100.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null);
        AfterSalesRule newer = rule(
                "T020-VERSIONED",
                2,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                "500.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null);

        // 两个版本都在生效窗口内属于历史版本共存的正常状态；结论必须与列表顺序无关。
        RuleSelection selection = EligibilityService.selectRule(shippedOrder("199.00"), List.of(older, newer), NOW);

        assertTrue(selection.isSelected());
        assertEquals(2, selection.rule().getVersion());
    }

    @Test
    void aRuleWithoutCategoryAppliesToAnyCategory() {
        AfterSalesRule wildcard = refundRule("T020-WILDCARD", 1, null, OrderStatus.SHIPPED);

        RuleSelection selection = EligibilityService.selectRule(
                order(OrderStatus.SHIPPED, "199.00", null, "HOME"), List.of(wildcard), NOW);

        assertTrue(selection.isSelected());
        assertEquals("T020-WILDCARD", selection.rule().getRuleCode());
    }

    @Test
    void oneOrderMatchingTwoDistinctRuleCodesCannotBeDecidedAutomatically() {
        AfterSalesRule first = refundRule("T020-CONFLICT-A", 1, "ELECTRONICS", OrderStatus.SHIPPED);
        AfterSalesRule second = refundRule("T020-CONFLICT-B", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        RuleSelection selection = EligibilityService.selectRule(shippedOrder("199.00"), List.of(first, second), NOW);

        assertEquals(RuleSelection.Status.CONFLICTING_RULES, selection.status());

        // 任意挑一条会让"用户能退多少钱"取决于规则行的插入顺序。转人工，并且不引用任何一条规则。
        EligibilityDecision decision =
                EligibilityService.decide(shippedOrder("199.00"), selection, stalledLogistics(120), NOW);
        assertFalse(decision.eligible());
        assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction());
        assertNull(decision.ruleCode());
        assertEquals(List.of(EligibilityReasonCode.CONFLICTING_RULES), decision.reasonCodes());
    }

    @Test
    void aCategoryRuleForAnotherOrderStateDoesNotSilentlyBecomeEligible() {
        AfterSalesRule shippedOnly = refundRule("T020-SHIPPED-ONLY", 1, "ELECTRONICS", OrderStatus.SHIPPED);
        OrderSnapshot delivered = order(OrderStatus.DELIVERED, "199.00", null, "ELECTRONICS");

        RuleSelection selection = EligibilityService.selectRule(delivered, List.of(shippedOnly), NOW);

        // 关键词是"另一格"：类目匹配上了、状态没匹配上。它与"整个类目没有规则"必须可区分，因为 US2 要靠这个
        // 信号把退款路径改道到退货路径。
        assertEquals(RuleSelection.Status.ORDER_STATE_NOT_ELIGIBLE, selection.status());

        EligibilityDecision decision = EligibilityService.decide(delivered, selection, null, NOW);
        assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction());
        assertEquals(List.of(EligibilityReasonCode.ORDER_STATE_NOT_ELIGIBLE), decision.reasonCodes());
    }

    @Test
    void noRuleAtAllIsReportedAsNoApplicableRule() {
        AfterSalesRule homeOnly = refundRule("T020-HOME-ONLY", 1, "HOME", OrderStatus.SHIPPED);

        RuleSelection selection = EligibilityService.selectRule(shippedOrder("199.00"), List.of(homeOnly), NOW);

        assertEquals(RuleSelection.Status.NO_APPLICABLE_RULE, selection.status());
        assertEquals(
                List.of(EligibilityReasonCode.NO_APPLICABLE_RULE),
                EligibilityService.decide(shippedOrder("199.00"), selection, null, NOW)
                        .reasonCodes());
    }

    // ------------------------------------------------------------------
    // 决策：证据段
    // ------------------------------------------------------------------

    @Test
    void stalledShippedOrderIsEligibleForARefund() {
        AfterSalesRule rule = refundRule("T020-STALLED", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("199.00"), rule, stalledLogistics(120));

        assertTrue(decision.eligible());
        assertTrue(decision.grantsMoneyAction());
        assertEquals(AllowedAction.REFUND_ONLY, decision.allowedAction());
        assertEquals(0, decision.maxRefundAmount().compareTo(new BigDecimal("199.00")));
        assertFalse(decision.approvalRequired());
        assertEquals("T020-STALLED", decision.ruleCode());
        assertEquals(1, decision.ruleVersion());
        assertEquals(List.of(EligibilityReasonCode.STALL_THRESHOLD_MET), decision.reasonCodes());
        assertEquals(NOW, decision.evaluatedAt());
    }

    @Test
    void theStallThresholdIsInclusiveSoExactlyFortyEightHoursQualifies() {
        AfterSalesRule rule = refundRule("T020-BOUNDARY", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("199.00"), rule, stalledLogistics(48));

        assertTrue(decision.eligible(), "48 小时整必须算达到 48 小时阈值：阈值比较取等号（与 T019 的口径一致）");
    }

    @Test
    void justUnderTheStallThresholdIsDeniedInsteadOfEscalated() {
        AfterSalesRule rule = refundRule("T020-BOUNDARY", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("199.00"), rule, stalledLogistics(47));

        assertFalse(decision.eligible());
        assertEquals(AllowedAction.DENY, decision.allowedAction(), "证据明确显示未达阈值，这是'证明不符合'，不是'不知道'");
        assertNull(decision.maxRefundAmount());
        assertFalse(decision.approvalRequired());
        assertEquals(List.of(EligibilityReasonCode.STALL_THRESHOLD_NOT_MET), decision.reasonCodes());
    }

    @Test
    void unknownStallDurationAsksForAHumanInsteadOfDenying() {
        AfterSalesRule rule = refundRule("T020-NO-EVIDENCE", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        // T019 已经钉死："没有物流事件"返回 null（不知道），而不是 0（刚刚有动静）。资格层必须保留这个区别。
        EligibilityDecision decision = decide(shippedOrder("199.00"), rule, noLogisticsEvidence());

        assertFalse(decision.eligible());
        assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction());
        assertEquals("T020-NO-EVIDENCE", decision.ruleCode(), "结论是'这条规则下的证据不足'，因此仍然引用这条规则");
        assertEquals(List.of(EligibilityReasonCode.LOGISTICS_EVIDENCE_UNAVAILABLE), decision.reasonCodes());
    }

    @Test
    void logisticsThatContradictTheOrderStateAreNeverTreatedAsStale() {
        AfterSalesRule rule = refundRule("T020-CONTRADICTION", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        // 订单行说 SHIPPED，运单说已签收。两个权威来源冲突时选错方向就是"给已签收订单退款"。
        EligibilityDecision decision =
                decide(shippedOrder("199.00"), rule, new LogisticsSnapshot(ShipmentStatus.DELIVERED, true, null, null));

        assertFalse(decision.eligible());
        assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction());
        assertEquals(List.of(EligibilityReasonCode.LOGISTICS_CONFLICTS_WITH_ORDER), decision.reasonCodes());
    }

    // ------------------------------------------------------------------
    // 决策：金额段
    // ------------------------------------------------------------------

    @Test
    void theApprovalThresholdIsInclusive() {
        AfterSalesRule rule = refundRule("T020-APPROVAL", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("300.00"), rule, stalledLogistics(120));

        assertTrue(decision.eligible(), "'达到高风险阈值'包含正好等于阈值：金额边界往更保守的方向取");
        assertTrue(decision.approvalRequired());
        assertTrue(decision.grantsMoneyAction(), "审批要求的含义是'资格允许但必须先拿到审批'，不是'没有资格'");
        assertEquals(0, decision.maxRefundAmount().compareTo(new BigDecimal("300.00")));
        assertEquals(
                List.of(EligibilityReasonCode.STALL_THRESHOLD_MET, EligibilityReasonCode.APPROVAL_REQUIRED_BY_AMOUNT),
                decision.reasonCodes());
    }

    @Test
    void anAmountBelowTheApprovalThresholdNeedsNoApproval() {
        AfterSalesRule rule = refundRule("T020-APPROVAL", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("299.99"), rule, stalledLogistics(120));

        assertTrue(decision.eligible());
        assertFalse(decision.approvalRequired());
        assertEquals(List.of(EligibilityReasonCode.STALL_THRESHOLD_MET), decision.reasonCodes());
    }

    @Test
    void anAmountAboveTheRuleLimitIsDeniedInsteadOfPartiallyRefunded() {
        AfterSalesRule rule = refundRule("T020-LIMIT", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("600.00"), rule, stalledLogistics(120));

        assertFalse(decision.eligible());
        assertEquals(AllowedAction.DENY, decision.allowedAction());
        assertNull(decision.maxRefundAmount(), "被拒绝的决策不得携带金额：否则下游可以绕过 eligible 直接用这个数");
        assertFalse(decision.approvalRequired(), "规则上限是硬边界，不是'需要人批一下'");
        assertEquals(
                List.of(EligibilityReasonCode.STALL_THRESHOLD_MET, EligibilityReasonCode.AMOUNT_EXCEEDS_RULE_LIMIT),
                decision.reasonCodes(),
                "拒绝前已经确认过的证据段结论必须保留，Trace 才能还原系统当时知道什么");
    }

    @Test
    void anAmountExactlyAtTheRuleLimitIsStillEligible() {
        AfterSalesRule rule = refundRule("T020-LIMIT", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        EligibilityDecision decision = decide(shippedOrder("500.00"), rule, stalledLogistics(120));

        assertTrue(decision.eligible(), "上限是闭区间端点：正好等于上限不构成'超过'");
        assertEquals(0, decision.maxRefundAmount().compareTo(new BigDecimal("500.00")));
        assertTrue(decision.approvalRequired());
    }

    @Test
    void aRuleWithoutACapStillCannotAuthoriseMoreThanTheOrderTotal() {
        AfterSalesRule unlimited = rule(
                "T020-NO-CAP",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                48,
                null,
                null,
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null);

        EligibilityDecision decision = decide(shippedOrder("199.00"), unlimited, stalledLogistics(120));

        // "规则没有声明上限"的语义是"这条规则不再进一步收窄"，不是"可以退任意金额"。真正的上界永远是订单总额。
        assertTrue(decision.eligible());
        assertEquals(0, decision.maxRefundAmount().compareTo(new BigDecimal("199.00")));
        assertFalse(decision.approvalRequired());
    }

    // ------------------------------------------------------------------
    // 决策：规则段
    // ------------------------------------------------------------------

    @Test
    void anOrderThatAlreadyStartedAfterSalesIsDeniedBeforeAnythingElse() {
        AfterSalesRule rule = refundRule("T020-DUPLICATE", 1, "ELECTRONICS", OrderStatus.SHIPPED);
        OrderSnapshot alreadyRefunded =
                order(OrderStatus.SHIPPED, "199.00", AfterSalesStatus.REFUND_REQUESTED, "ELECTRONICS");

        // 物流事实刻意传 null：已有售后是终止性结论，决策层不应该、也不需要读到物流那一步。
        EligibilityDecision decision =
                EligibilityService.decide(alreadyRefunded, RuleSelection.selected(rule), null, NOW);

        assertEquals(AllowedAction.DENY, decision.allowedAction());
        assertEquals(List.of(EligibilityReasonCode.ORDER_ALREADY_HAS_AFTER_SALES), decision.reasonCodes());
    }

    @Test
    void aRuleWhoseActionIsDenyIsReportedAsDenied() {
        AfterSalesRule denyRule = rule(
                "T020-DENY",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                null,
                null,
                null,
                AllowedAction.DENY,
                true,
                EFFECTIVE_FROM,
                null);

        EligibilityDecision decision = decide(shippedOrder("199.00"), denyRule, null);

        assertFalse(decision.eligible());
        assertEquals(AllowedAction.DENY, decision.allowedAction());
        assertEquals(List.of(EligibilityReasonCode.RULE_ACTION_DENY), decision.reasonCodes());
    }

    @Test
    void aRuleWhoseActionIsManualReviewAsksForAHuman() {
        AfterSalesRule manualRule = rule(
                "T020-MANUAL",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                null,
                null,
                null,
                AllowedAction.MANUAL_REVIEW,
                true,
                EFFECTIVE_FROM,
                null);

        EligibilityDecision decision = decide(shippedOrder("199.00"), manualRule, null);

        assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction());
        assertEquals("T020-MANUAL", decision.ruleCode());
        assertEquals(List.of(EligibilityReasonCode.RULE_ACTION_MANUAL_REVIEW), decision.reasonCodes());
    }

    @Test
    void aReturnRuleIsNotSilentlyExecutedAsARefund() {
        OrderSnapshot delivered = order(OrderStatus.DELIVERED, "199.00", null, "ELECTRONICS");
        AfterSalesRule returnRule = rule(
                "T020-RETURN",
                1,
                "ELECTRONICS",
                OrderStatus.DELIVERED,
                null,
                "500.00",
                "300.00",
                AllowedAction.RETURN,
                true,
                EFFECTIVE_FROM,
                null);
        AfterSalesRule returnRefundRule = rule(
                "T020-RETURN-REFUND",
                1,
                "ELECTRONICS",
                OrderStatus.DELIVERED,
                null,
                "500.00",
                "300.00",
                AllowedAction.RETURN_REFUND,
                true,
                EFFECTIVE_FROM,
                null);

        // 本版本只实现了退款所需的证据校验：退货窗口判定属于 T039。在没有那套校验之前宁可转人工，
        // 也不能因为规则行写着 RETURN 就自动放行。
        for (AfterSalesRule rule : List.of(returnRule, returnRefundRule)) {
            EligibilityDecision decision = decide(delivered, rule, null);
            assertEquals(AllowedAction.MANUAL_REVIEW, decision.allowedAction(), rule.getRuleCode());
            assertEquals(List.of(EligibilityReasonCode.RULE_ACTION_NOT_SUPPORTED), decision.reasonCodes());
            assertFalse(decision.eligible(), "未实现的动作不得被视为已批准");
        }
    }

    // ------------------------------------------------------------------
    // 证据收集范围与确定性
    // ------------------------------------------------------------------

    @Test
    void aRuleWithoutAStallRequirementIsDecidedWithoutLogisticsFacts() {
        AfterSalesRule noStallRule = rule(
                "T020-NO-STALL",
                1,
                "ELECTRONICS",
                OrderStatus.SHIPPED,
                null,
                "500.00",
                null,
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null);
        OrderSnapshot order = shippedOrder("199.00");
        RuleSelection selection = RuleSelection.selected(noStallRule);

        // 关键断言是"物流事实可以是 null"：如果外壳无条件去读物流，一个不需要物流的规则会被一次物流依赖故障
        // 拖成 503，把本来能确定性回答的问题变成失败。
        assertFalse(EligibilityService.needsLogisticsFacts(order, selection));
        assertTrue(EligibilityService.needsLogisticsFacts(
                order,
                RuleSelection.selected(refundRule("T020-NEEDS-LOGISTICS", 1, "ELECTRONICS", OrderStatus.SHIPPED))));

        EligibilityDecision decision = EligibilityService.decide(order, selection, null, NOW);
        assertTrue(decision.eligible());
        assertEquals(List.of(), decision.reasonCodes(), "规则没有声明任何条件时，批准结论的解释就在 ruleCode/金额上，不硬塞一个填充原因码");
    }

    @Test
    void aRuleThatNeedsStallEvidenceRefusesToDecideWithoutIt() {
        AfterSalesRule rule = refundRule("T020-REQUIRES-LOGISTICS", 1, "ELECTRONICS", OrderStatus.SHIPPED);

        // 这是实现缺陷（外壳与决策层的前置条件漂移），不是业务结论：必须炸，而不是编一个"没证据"的决策。
        assertThrows(
                IllegalArgumentException.class,
                () -> EligibilityService.decide(shippedOrder("199.00"), RuleSelection.selected(rule), null, NOW));
    }

    @Test
    void repeatingTheSameEvaluationYieldsTheSameDecision() {
        AfterSalesRule rule = refundRule("T020-DETERMINISTIC", 1, "ELECTRONICS", OrderStatus.SHIPPED);
        OrderSnapshot order = shippedOrder("199.00");
        LogisticsSnapshot logistics = stalledLogistics(120);

        EligibilityDecision first = decide(order, rule, logistics);
        EligibilityDecision second = decide(order, rule, logistics);

        assertEquals(first, second, "同样的权威事实必须得到完全相同的决策，包括原因码与时间戳");
    }

    @Test
    void decisionsThatContradictThemselvesCannotBeConstructed() {
        List<EligibilityReasonCode> reasons = List.of(EligibilityReasonCode.STALL_THRESHOLD_MET);
        BigDecimal amount = new BigDecimal("199.00");

        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(true, AllowedAction.DENY, null, false, "R", 1, reasons, NOW),
                "eligible=true 与 allowedAction=DENY 不能共存");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(false, AllowedAction.REFUND_ONLY, null, false, "R", 1, reasons, NOW),
                "eligible=false 与一个已批准的动作不能共存");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(false, AllowedAction.DENY, amount, false, "R", 1, reasons, NOW),
                "被拒绝的决策不得携带可退金额");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(false, AllowedAction.MANUAL_REVIEW, null, true, "R", 1, reasons, NOW),
                "转人工的决策不得携带'需要审批'");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(true, AllowedAction.REFUND_ONLY, amount, false, null, null, reasons, NOW),
                "任何批准动作都必须引用产生它的规则行");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(true, AllowedAction.REFUND_ONLY, amount, false, "R", null, reasons, NOW),
                "ruleCode 与 ruleVersion 要么都给，要么都不给");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(true, AllowedAction.REFUND_ONLY, null, false, "R", 1, reasons, NOW),
                "会移动资金的动作必须有金额上界");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(true, AllowedAction.RETURN, amount, false, "R", 1, reasons, NOW),
                "纯退货动作不携带退款金额");
        assertThrows(
                IllegalArgumentException.class,
                () -> new EligibilityDecision(false, AllowedAction.DENY, null, false, "R", 1, List.of(), NOW),
                "拒绝必须能解释自己：没有原因码的拒绝在 Trace 与 Eval 里无法归因");

        EligibilityDecision pureReturn =
                new EligibilityDecision(true, AllowedAction.RETURN, null, false, "R", 1, reasons, NOW);
        assertTrue(pureReturn.eligible());
        assertFalse(pureReturn.grantsMoneyAction(), "退货是动作，不是资金授权");

        EligibilityDecision conditionFreeGrant =
                new EligibilityDecision(true, AllowedAction.REFUND_ONLY, amount, false, "R", 1, List.of(), NOW);
        assertTrue(conditionFreeGrant.reasonCodes().isEmpty(), "规则没有声明任何条件时，批准决策允许不带原因码：解释已经在 ruleCode 与金额上");
    }

    // ------------------------------------------------------------------
    // 夹具
    // ------------------------------------------------------------------

    private static EligibilityDecision decide(OrderSnapshot order, AfterSalesRule rule, LogisticsSnapshot logistics) {
        return EligibilityService.decide(order, RuleSelection.selected(rule), logistics, NOW);
    }

    private static OrderSnapshot shippedOrder(String totalAmount) {
        return order(OrderStatus.SHIPPED, totalAmount, null, "ELECTRONICS");
    }

    private static OrderSnapshot order(
            OrderStatus status, String totalAmount, AfterSalesStatus afterSalesStatus, String... categories) {
        List<OrderSnapshot.Item> items = java.util.stream.IntStream.range(0, categories.length)
                .mapToObj(index -> new OrderSnapshot.Item("product-" + index, "Product " + index, categories[index], 1))
                .toList();
        return new OrderSnapshot(
                "order-under-test", status, new BigDecimal(totalAmount), "USD", afterSalesStatus, items);
    }

    private static LogisticsSnapshot stalledLogistics(long stalledHours) {
        return new LogisticsSnapshot(
                ShipmentStatus.IN_TRANSIT, false, NOW.minus(Duration.ofHours(stalledHours)), stalledHours);
    }

    private static LogisticsSnapshot noLogisticsEvidence() {
        return new LogisticsSnapshot(ShipmentStatus.CREATED, false, null, null);
    }

    /** 夹具规则统一使用 48 小时停滞阈值、500.00 上限、300.00 审批阈值，个别用例再按需覆盖。 */
    private static AfterSalesRule refundRule(
            String ruleCode, int version, String productCategory, OrderStatus requiredOrderStatus) {
        return rule(
                ruleCode,
                version,
                productCategory,
                requiredOrderStatus,
                48,
                "500.00",
                "300.00",
                AllowedAction.REFUND_ONLY,
                true,
                EFFECTIVE_FROM,
                null);
    }

    private static AfterSalesRule rule(
            String ruleCode,
            int version,
            String productCategory,
            OrderStatus requiredOrderStatus,
            Integer logisticsStalledHours,
            String maxRefundAmount,
            String approvalThreshold,
            AllowedAction allowedAction,
            boolean active,
            Instant effectiveFrom,
            Instant effectiveTo) {
        return AfterSalesRule.create(
                ruleCode,
                version,
                productCategory,
                requiredOrderStatus,
                logisticsStalledHours,
                7,
                amount(maxRefundAmount),
                amount(approvalThreshold),
                allowedAction,
                active,
                effectiveFrom,
                effectiveTo);
    }

    private static BigDecimal amount(String value) {
        return value == null ? null : new BigDecimal(value);
    }
}
